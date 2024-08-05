#!/usr/bin/env python
from zeeguu.api.app import create_app
from zeeguu.core.model import Feed, Url, Language
from zeeguu.core.feed_handler import FEED_TYPE
import zeeguu.core

app = create_app()
app.app_context().push()


def create_and_test_feed(url: str, feed_type: int, skip_feed: bool):
    feed = Feed.from_url(url, feed_type=feed_type)
    if not skip_feed:
        print(feed.feed_health_info())

    return feed


def main():
    _feed_url = input("Feed url:  ")
    print(f"Available feed types: '{FEED_TYPE}'")
    feed_type = int(input("What feed type is it? : "))
    skip_feed = int(input("Do you want to skip testing the feed? (1:yes, else:no)"))
    test_feed = create_and_test_feed(_feed_url, feed_type, skip_feed == 1)

    feed_name = input(f"Feed name (Enter for: {test_feed.title}):  ") or test_feed.title
    print(f"= {feed_name}")

    default_icon_name = "_".join(feed_name.split()) + ".png"
    icon_name = (
        input(
            f"Icon name to be found in resources folder (Enter for: {default_icon_name}):  "
        )
        or default_icon_name
    )
    print(f"= {icon_name}")

    description = (
        input(f"Description (Enter for: {test_feed.description}): ")
        or test_feed.description
    )
    print(f"= {description}")

    _language = input("Language code (e.g. en): ")
    print(f"= {_language}")

    feed_url = Url.find_or_create(zeeguu.core.model.db.session, _feed_url)
    language = Language.find_or_create(_language)

    feed = Feed.find_or_create(
        zeeguu.core.model.db.session,
        feed_url,
        feed_name,
        description,
        icon_name=icon_name,
        language=language,
        feed_type=feed_type,
    )

    print("Done: ")
    print(feed.title)
    print(feed.description)
    print(feed.language_id)
    print(feed.url.as_string())


if __name__ == "__main__":
    main()
