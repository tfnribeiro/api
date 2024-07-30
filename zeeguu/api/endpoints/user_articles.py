import flask

from zeeguu.core.content_recommender import (
    article_recommendations_for_user,
    topic_filter_for_user,
    content_recommendations,
    find_articles_like,
)
from zeeguu.core.model import UserArticle, Article, PersonalCopy, User
from zeeguu.core.content_recommender.elastic_recommender import find_articles_like

from zeeguu.api.utils.route_wrappers import cross_domain, requires_session
from zeeguu.api.utils.json_result import json_result
from sentry_sdk import capture_exception
from . import api

from flask import request


# ---------------------------------------------------------------------------
@api.route("/user_articles/recommended", methods=("GET",))
@api.route("/user_articles/recommended/<int:count>", methods=("GET",))
@api.route("/user_articles/recommended/<int:count>/<int:page>", methods=("GET",))
# ---------------------------------------------------------------------------
@cross_domain
@requires_session
def user_articles_recommended(count: int = 20, page: int = 0):
    """
    recommendations for all languages
    """
    user = User.find_by_id(flask.g.user_id)
    try:
        articles = article_recommendations_for_user(user, count, page)

    except:
        # we failed to get recommendations from elastic
        # return something
        articles = (
            Article.query.filter_by(broken=0)
            .filter_by(language_id=user.learned_language_id)
            .order_by(Article.published_time.desc())
            .limit(20)
        )

    article_infos = [UserArticle.user_article_info(user, a) for a in articles]

    return json_result(article_infos)


@api.route("/user_articles/saved", methods=["GET"])
@cross_domain
@requires_session
def saved_articles():
    user = User.find_by_id(flask.g.user_id)
    saves = PersonalCopy.all_for(user)

    article_infos = [UserArticle.user_article_info(user, e) for e in saves]

    return json_result(article_infos)


# ---------------------------------------------------------------------------
@api.route("/user_articles/topic_filtered", methods=("POST",))
# ---------------------------------------------------------------------------
@cross_domain
@requires_session
def user_articles_topic_filtered():
    """
    recommendations based on filters coming from the UI
    """
    MAX_ARTICLES_PER_TOPIC = 20

    topic = request.form.get("topic")
    newer_than = request.form.get("newer_than", None)
    media_type = request.form.get("media_type", None)
    max_duration = request.form.get("max_duration", None)
    min_duration = request.form.get("min_duration", None)
    difficulty_level = request.form.get("difficulty_level", None)
    user = User.find_by_id(flask.g.user_id)

    articles = topic_filter_for_user(
        user,
        MAX_ARTICLES_PER_TOPIC,
        newer_than,
        media_type,
        max_duration,
        min_duration,
        difficulty_level,
        topic,
    )
    article_infos = [UserArticle.user_article_info(user, a) for a in articles]

    return json_result(article_infos)


# ---------------------------------------------------------------------------
@api.route("/user_articles/starred_or_liked", methods=("GET",))
# ---------------------------------------------------------------------------
@cross_domain
@requires_session
def user_articles_starred_and_liked():
    user = User.find_by_id(flask.g.user_id)
    return json_result(UserArticle.all_starred_and_liked_articles_of_user_info(user))


# ---------------------------------------------------------------------------
@api.route("/cohort_articles", methods=("GET",))
# ---------------------------------------------------------------------------
@cross_domain
@requires_session
def user_articles_cohort():
    """
    get all articles for the cohort associated with the user
    """
    user = User.find_by_id(flask.g.user_id)
    return json_result(user.cohort_articles_for_user())


# ---------------------------------------------------------------------------
@api.route("/get_similar_articles", methods=("GET",))
# ---------------------------------------------------------------------------
@cross_domain
@requires_session
def similar_articles_to_article():
    user = User.find_by_id(flask.g.user_id)
    article_id = request.args.get("article_id", "")
    print(request.args)
    rel_difficulty = request.args.get("rel_dif", 3)
    if rel_difficulty == "undefined":
        rel_difficulty = 3
    else:
        rel_difficulty = int(rel_difficulty)
    article = Article.find_by_id(article_id)
    print("Giving similar articles!")
    try:
        articles = find_articles_like(
            [article_id],
            2,
            365,
            article.language_id,
            article.fk_difficulty,
            rel_difficulty,
        )
    except Exception as e:
        print(e)
        capture_exception(e)
        # Usually no recommendations when the user has not liked any articles
        articles = []
    article_infos = [UserArticle.user_article_info(user, a) for a in articles]

    return json_result(article_infos)


# ---------------------------------------------------------------------------
@api.route("/user_articles/foryou", methods=("GET",))
# ---------------------------------------------------------------------------
@cross_domain
@requires_session
def user_articles_foryou():
    article_infos = []
    user = User.find_by_id(flask.g.user_id)
    try:
        articles = content_recommendations(user.id, user.learned_language_id)
        print("Sending CB recommendations")
    except Exception as e:
        print(e)
        capture_exception(e)
        # Usually no recommendations when the user has not liked any articles
        articles = []
    article_infos = [UserArticle.user_article_info(user, a) for a in articles]

    return json_result(article_infos)
