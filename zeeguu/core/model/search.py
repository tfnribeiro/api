import sqlalchemy
from zeeguu.api.utils.abort_handling import make_error
import zeeguu.core
from sqlalchemy import Column, Integer, String

from zeeguu.core.model import db


class Search(db.Model):
    """

    A search is string which any user can enter.
    When searched, it won't be entered in the DB yet.
    Only when a user subscribes or filters a search.
    When subscribing, the articles are also mapped to the search.
    When unsubscribed, the search is deleted.

    """

    __table_args__ = {"mysql_collate": "utf8_bin"}

    id = Column(Integer, primary_key=True)

    keywords = Column(String(100))

    def __init__(self, keywords):
        self.keywords = keywords

    def __repr__(self):
        return f"<Search: {self.keywords}>"

    def as_dictionary(self):

        return dict(
            id=self.id,
            search=self.keywords,
        )

    def all_articles(self):
        from zeeguu.core.model import Article

        return Article.query.filter(Article.searches.any(id=self.id)).all()

    @classmethod
    def find_or_create(cls, session, keywords):
        try:
            return cls.query.filter(cls.keywords == keywords).one()
        except sqlalchemy.orm.exc.NoResultFound:
            new = cls(keywords)
            session.add(new)
            session.commit()
            return new

    @classmethod
    def find(cls, keywords):
        try:
            search = cls.query.filter(cls.keywords == keywords).one()
            return search
        except sqlalchemy.orm.exc.NoResultFound:
            return None

    @classmethod
    def find_by_id(cls, i):
        try:
            result = cls.query.filter(cls.id == i).one()
            return result
        except Exception as e:
            from sentry_sdk import capture_exception

            capture_exception(e)
            return None
    