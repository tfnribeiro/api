"""

    Goes through all the interesting sources that the server knows
    about and downloads new articles saving them in the DB.  


"""

import newspaper

from pymysql import DataError

from zeeguu.logging import log, logp

from zeeguu.core import model
from zeeguu.core.content_quality.quality_filter import sufficient_quality
from zeeguu.core.emailer.zeeguu_mailer import ZeeguuMailer
from zeeguu.core.model import Url, RSSFeed, LocalizedTopic
from langdetect import detect
import requests

from zeeguu.core.model.article import MAX_CHAR_COUNT_IN_SUMMARY

from zeeguu.core.model.difficulty_lingo_rank import DifficultyLingoRank
from sentry_sdk import capture_exception as capture_to_sentry
from zeeguu.core.elastic.indexing import index_in_elasticsearch

from zeeguu.core.content_retriever import download_and_parse, TIMEOUT_SECONDS

import zeeguu

LOG_CONTEXT = "FEED RETRIEVAL"


class SkippedForTooOld(Exception):
    pass


class SkippedForLowQuality(Exception):
    def __init__(self, reason):
        self.reason = reason

class SkippedForLanguageMismatch(Exception):
    pass

class SkippedAlreadyInDB(Exception):
    pass


def _url_after_redirects(url):
    # solve redirects and save the clean url
    response = requests.get(url)
    return response.url


def _date_in_the_future(time):
    from datetime import datetime

    return time > datetime.now()


def banned_url(url):
    banned = [
        "https://www.dr.dk/sporten/seneste-sport/",
        "https://www.dr.dk/nyheder/seneste/",
    ]
    for each in banned:
        if url.startswith(each):
            return True
    return False


def download_from_feed(feed: RSSFeed, session, limit=1000, save_in_elastic=True):
    """

    Session is needed because this saves stuff to the DB.


    last_crawled_time is useful because otherwise there would be a lot of time
    wasted trying to retrieve the same articles, especially the ones which
    can't be retrieved, so they won't be cached.


    """

    print(feed.url)

    downloaded = 0
    skipped_due_to_low_quality = 0
    skipped_already_in_db = 0

    last_retrieval_time_from_DB = None
    last_retrieval_time_seen_this_crawl = None

    if feed.last_crawled_time:
        last_retrieval_time_from_DB = feed.last_crawled_time
        log(f"LAST CRAWLED::: {last_retrieval_time_from_DB}")

    try:
        items = feed.feed_items(last_retrieval_time_from_DB)
    except Exception as e:
        import traceback

        traceback.print_stack()
        capture_to_sentry(e)
        return

    for feed_item in items:

        skipped_already_in_db = 0

        if downloaded >= limit:
            break

        feed_item_timestamp = feed_item["published_datetime"]

        if _date_in_the_future(feed_item_timestamp):
            log("Article from the future!")
            continue

        if (not last_retrieval_time_seen_this_crawl) or (
                feed_item_timestamp > last_retrieval_time_seen_this_crawl
        ):
            last_retrieval_time_seen_this_crawl = feed_item_timestamp

        if last_retrieval_time_seen_this_crawl > feed.last_crawled_time:
            feed.last_crawled_time = last_retrieval_time_seen_this_crawl
            log(
                f"+updated feed's last crawled time to {last_retrieval_time_seen_this_crawl}"
            )

        try:
            log("before redirects")
            log(feed_item["url"])
            url = _url_after_redirects(feed_item["url"])
            logp("===============================> ")
            logp("after redirects")
            logp(url)

        except requests.exceptions.TooManyRedirects:
            raise Exception(f"- Too many redirects")
        except Exception:
            raise Exception(
                f"- Could not get url after redirects for {feed_item['url']}"
            )

        if banned_url(url):
            logp("Banned Url")
            continue

        session.add(feed)
        session.commit()

        try:
            new_article = download_feed_item(session, feed, feed_item, url)
            downloaded += 1
            if save_in_elastic:
                if new_article:
                    index_in_elasticsearch(new_article, session)

            if new_article:
                ZeeguuMailer.send_content_retrieved_notification(new_article)

        except SkippedForTooOld:
            logp("- Article too old")
            continue
        except SkippedForLowQuality as e:
            logp(f" - Low quality: {e.reason}")
            skipped_due_to_low_quality += 1
            continue
        except SkippedAlreadyInDB:
            skipped_already_in_db += 1
            logp(" - Already in DB")
            continue

        except Exception as e:
            import traceback

            traceback.print_stack()

            capture_to_sentry(e)

            if hasattr(e, "message"):
                logp(e.message)
            else:
                logp(e)
            continue

    logp(f"*** Downloaded: {downloaded} From: {feed.title}")
    logp(f"*** Low Quality: {skipped_due_to_low_quality}")
    logp(f"*** Already in DB: {skipped_already_in_db}")
    logp(f"*** ")


def download_feed_item(session, feed, feed_item, url):
    new_article = None

    title = feed_item["title"]

    published_datetime = feed_item["published_datetime"]

    try:
        art = model.Article.find(url)
    except:
        import sys

        ex = sys.exc_info()[0]
        raise Exception(
            f" {LOG_CONTEXT}: For some reason excepted during Article.find \n{str(ex)}"
        )

    if art:
        raise SkippedAlreadyInDB()

    try:

        parsed = download_and_parse(url)

        is_quality_article, reason = sufficient_quality(parsed)
        article_detected_lang = detect(parsed)

        if article_detected_lang != feed.language.code:
            raise SkippedForLanguageMismatch
        
        if not is_quality_article:
            raise SkippedForLowQuality(reason)

        summary = feed_item["summary"]
        # however, this is not so easy... there have been cases where
        # the summary is just malformed HTML... thus we try to extract
        # the text:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(summary, "lxml")
        summary = soup.get_text()
        # then there are cases where the summary is huge... so we clip it
        summary = summary[:MAX_CHAR_COUNT_IN_SUMMARY]
        # and if there is still no summary, we simply use the beginning of
        # the article
        if len(summary) < 10:
            summary = parsed.text[:MAX_CHAR_COUNT_IN_SUMMARY]

            # Create new article and save it to DB
        new_article = zeeguu.core.model.Article(
            Url.find_or_create(session, url),
            title,
            ", ".join(parsed.authors),
            parsed.text,
            summary,
            published_datetime,
            feed,
            feed.language,
        )
        session.add(new_article)

        topics = add_topics(new_article, session)
        logp(f" Topics ({topics})")

        # compute extra difficulties for french articles
        try:
            if new_article.language.code == "fr":
                from zeeguu.core.language.services.lingo_rank_service import (
                    retrieve_lingo_rank,
                )

                df = DifficultyLingoRank(
                    new_article, retrieve_lingo_rank(new_article.content)
                )
                session.add(df)
        except Exception as e:
            capture_to_sentry(e)

        session.commit()
        logp(f"SUCCESS for: {new_article.title}")

    except SkippedForLowQuality as e:
        raise e

    except newspaper.ArticleException as e:
        logp(f"can't download article at: {url}")

    except DataError as e:
        logp(f"Data error for: {url}")

    except requests.exceptions.Timeout:
        logp(f"The request from the server was timed out after {TIMEOUT_SECONDS} seconds.")
        
    except Exception as e:
        import traceback

        traceback.print_exc()
        capture_to_sentry(e)

        log(
            f"* Rolling back session due to exception while creating article and attaching words/topics: {str(e)}"
        )
        session.rollback()

    return new_article


def add_topics(new_article, session):
    topics = []
    for loc_topic in LocalizedTopic.query.all():
        if loc_topic.language == new_article.language and loc_topic.matches_article(
                new_article
        ):
            topics.append(loc_topic.topic.title)
            new_article.add_topic(loc_topic.topic)
            session.add(new_article)
    return topics
