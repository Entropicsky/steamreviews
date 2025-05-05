import datetime
from sqlalchemy import ( BigInteger, Boolean, Column, DateTime, ForeignKey,
                       Integer, Numeric, String, Text, create_engine )
from sqlalchemy.dialects.postgresql import ARRAY, TEXT as PG_TEXT # Use specific dialect types if needed
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.sql import func

Base = declarative_base()

class TrackedApp(Base):
    __tablename__ = 'tracked_apps'

    app_id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=True)
    added_at = Column(DateTime(timezone=True), server_default=func.now())
    is_active = Column(Boolean, default=True)

    reviews = relationship("Review", back_populates="app")

class Review(Base):
    __tablename__ = 'reviews'

    recommendationid = Column(BigInteger, primary_key=True, index=True)
    app_id = Column(Integer, ForeignKey('tracked_apps.app_id'), index=True)
    author_steamid = Column(String(30))
    original_language = Column(String(20), nullable=False, index=True)
    original_review_text = Column(Text, nullable=True)
    english_translation = Column(Text, nullable=True)
    translation_status = Column(String(20), default='pending', index=True)
    translation_model = Column(String(50), nullable=True)
    analysis_status = Column(String(20), default='pending', index=True)
    analyzed_sentiment = Column(String(20), nullable=True)
    # Use ARRAY(Text) for PostgreSQL TEXT arrays
    positive_themes = Column(ARRAY(PG_TEXT), nullable=True)
    negative_themes = Column(ARRAY(PG_TEXT), nullable=True)
    feature_requests = Column(ARRAY(PG_TEXT), nullable=True)
    bug_reports = Column(ARRAY(PG_TEXT), nullable=True)
    llm_analysis_model = Column(String(50), nullable=True)
    llm_analysis_timestamp = Column(DateTime(timezone=True), nullable=True)
    timestamp_created = Column(BigInteger, nullable=False, index=True)
    timestamp_updated = Column(BigInteger, nullable=False)
    voted_up = Column(Boolean, nullable=False)
    votes_up = Column(Integer, default=0)
    votes_funny = Column(Integer, default=0)
    weighted_vote_score = Column(Numeric(10, 9), default=0.0)
    comment_count = Column(Integer, default=0)
    steam_purchase = Column(Boolean, default=False)
    received_for_free = Column(Boolean, default=False)
    written_during_early_access = Column(Boolean, default=False)
    developer_response = Column(Text, nullable=True)
    timestamp_dev_responded = Column(BigInteger, nullable=True)
    author_num_games_owned = Column(Integer, default=0)
    author_num_reviews = Column(Integer, default=0)
    author_playtime_forever = Column(Integer, default=0)
    author_playtime_last_two_weeks = Column(Integer, default=0)
    author_playtime_at_review = Column(Integer, default=0)
    author_last_played = Column(BigInteger, default=0)
    db_inserted_at = Column(DateTime(timezone=True), server_default=func.now())
    db_last_updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    app = relationship("TrackedApp", back_populates="reviews")

    def to_dict(self):
        """Converts the SQLAlchemy model instance to a dictionary."""
        result = {}
        # Add Review fields from the table columns
        for key in self.__table__.columns.keys():
            result[key] = getattr(self, key)
        return result 