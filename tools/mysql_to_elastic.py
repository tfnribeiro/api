# coding=utf-8
from zeeguu.core.elastic.indexing import (
    create_or_update_bulk_docs,
)
from sqlalchemy import func
from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk, BulkIndexError
import zeeguu.core
from zeeguu.core.model import Article
import sys
from datetime import datetime
from sqlalchemy.orm.exc import NoResultFound
from zeeguu.api.app import create_app

from zeeguu.core.model import Topic
from zeeguu.core.model.article import article_topic_map
from zeeguu.core.elastic.settings import ES_ZINDEX, ES_CONN_STRING
import numpy as np

# PARAMS That can be Adjusted for the script.

DELETE_INDEX = False
TOTAL_ITEMS = "ALL"
ITERATION_STEP = 1000

app = create_app()
app.app_context().push()

print(ES_CONN_STRING)
es = Elasticsearch(ES_CONN_STRING)
db_session = zeeguu.core.model.db.session


def find_topics(article_id, session):
    article_topic = (
        session.query(Topic)
        .join(article_topic_map)
        .filter(article_topic_map.c.article_id == article_id)
    )
    topics = ""
    for t in article_topic:
        topics = topics + str(t.title) + " "

    return topics.rstrip()


def main():
    if DELETE_INDEX:
        try:
            es.indices.delete(index="zeeguu", ignore=[400, 404])
            print("Deleted index 'zeeguu'!")
        except Exception as e:
            print(f"Failed to delete: {e}")

    def fetch_articles_by_id(id_list):
        for i in id_list:
            try:
                if es.exists(index=ES_ZINDEX, id=i):
                    print(f"Skipped for: '{i}'")
                    continue
                article = Article.find_by_id(i)
                yield (article)
            except NoResultFound:
                print(f"fail for: '{i}'")
            except Exception as e:
                print(f"fail for: '{i}', {e}")

    def gen_docs(articles):
        for article in articles:
            try:
                yield create_or_update_bulk_docs(article, db_session)
            except Exception as e:
                print(f"fail for: '{article.id}', {e}")

    # Get All the IDs
    # You can alter the Query, to for example only index the DB articles for a language.
    # e.g. db_session.query(Article.id).filter(Article.language_id == 2).all() for DK only.
    all_article_ids = np.array([a_id[0] for a_id in db_session.query(Article.id).all()])
    # Filter can be used to retrieve specific language.
    print(f"Total Articles in DB: {len(all_article_ids)}")
    # Filter out those not in ES
    print("Filtering out articles already in ES.")
    all_article_ids_not_in_es = list(
        filter(lambda x: not es.exists(index=ES_ZINDEX, id=x), all_article_ids)
    )
    print("Total articles missing: ", len(all_article_ids_not_in_es))
    # I noticed that if a document is not added then it won't let me query the ES search.
    total_added = 0

    # Total Items to Handle
    total_items = (
        len(all_article_ids_not_in_es) if TOTAL_ITEMS == "ALL" else TOTAL_ITEMS
    )

    sampled_ids = np.random.choice(
        all_article_ids_not_in_es,
        min(total_items, len(all_article_ids_not_in_es)),
        replace=False,
    )
    for i_start in range(0, total_items, ITERATION_STEP):
        print(f"Starting at {i_start}")
        sub_sample = sampled_ids[i_start : i_start + ITERATION_STEP]
        try:
            res, _ = bulk(es, gen_docs(fetch_articles_by_id(sub_sample)))
            total_added += res
            print(f"Completed {i_start+ITERATION_STEP}/{total_items}...")
        except BulkIndexError:
            print("-- WARNING, at least one document failed to index.")
    print(f"Total articles added: {total_added}")


if __name__ == "__main__":
    print("waiting for the ES process to boot up")
    start = datetime.now()
    print(f"started at: {start}")
    main()
    end = datetime.now()
    print(f"ended at: {end}")
    print(f"Process took: {end-start}")
