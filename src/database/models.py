import datetime
from sqlalchemy import ( BigInteger, Boolean, Column, DateTime, ForeignKey,
                       Integer, Numeric, String, Text, create_engine, UniqueConstraint )
from sqlalchemy.dialects.postgresql import ARRAY, TEXT as PG_TEXT # Use specific dialect types if needed
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.sql import func

Base = declarative_base()

class TrackedApp(Base):
    __tablename__ = 'tracked_apps'

    app_id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True, index=True)
    last_fetched_timestamp = Column(BigInteger, default=0, index=True)
    last_processed_timestamp = Column(BigInteger, default=0, index=True) # For analysis/translation
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

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

# === New YouTube Feedback Models ===

class Game(Base):
    """Represents a game being tracked for feedback (Steam or YouTube)"""
    __tablename__ = 'games'

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False, unique=True)
    steam_app_id = Column(Integer, ForeignKey('tracked_apps.app_id'), nullable=True, unique=True) # Link to existing Steam app data if applicable
    slack_channel_id = Column(String(50), nullable=True) # For reporting
    is_active = Column(Boolean, default=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationship to allow finding which influencers are tracked for this game
    influencer_mappings = relationship("GameInfluencerMapping", back_populates="game")

class Influencer(Base):
    """Represents a YouTube influencer"""
    __tablename__ = 'influencers'

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False, unique=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationship to the channels associated with this influencer
    channels = relationship("YouTubeChannel", back_populates="influencer")
    # Relationship to allow finding which games this influencer is tracked for
    game_mappings = relationship("GameInfluencerMapping", back_populates="influencer")

class YouTubeChannel(Base):
    """Represents a specific YouTube channel, linked to an influencer"""
    __tablename__ = 'youtube_channels'

    id = Column(String(50), primary_key=True) # Supadata Channel ID (e.g., UCuAXFkgsw1L7xaCfnd5JJOw)
    influencer_id = Column(Integer, ForeignKey('influencers.id'), nullable=False)
    channel_name = Column(String(255), nullable=True)
    handle = Column(String(100), nullable=True, unique=True) # e.g., @RickAstley
    last_checked_timestamp = Column(BigInteger, default=0, index=True) # Store as UNIX timestamp (seconds)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    influencer = relationship("Influencer", back_populates="channels")
    videos = relationship("YouTubeVideo", back_populates="channel")

class GameInfluencerMapping(Base):
    """Many-to-many mapping between games and influencers"""
    __tablename__ = 'game_influencer_mappings'

    game_id = Column(Integer, ForeignKey('games.id'), primary_key=True)
    influencer_id = Column(Integer, ForeignKey('influencers.id'), primary_key=True)
    is_active = Column(Boolean, default=True, index=True) # Allows temporarily disabling tracking
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    game = relationship("Game", back_populates="influencer_mappings")
    influencer = relationship("Influencer", back_populates="game_mappings")

class YouTubeVideo(Base):
    """Represents a YouTube video fetched via Supadata"""
    __tablename__ = 'youtube_videos'

    id = Column(String(20), primary_key=True) # Supadata Video ID (e.g., dQw4w9WgXcQ)
    channel_id = Column(String(50), ForeignKey('youtube_channels.id'), nullable=False, index=True)
    title = Column(Text, nullable=True)
    description = Column(Text, nullable=True)
    upload_date = Column(DateTime(timezone=True), nullable=True, index=True) # Store as DateTime
    duration = Column(Integer, nullable=True) # Seconds
    transcript_status = Column(String(20), default='pending', index=True) # 'pending', 'fetched', 'failed', 'unavailable'
    analysis_status = Column(String(20), default='pending', index=True) # 'pending', 'analyzed', 'irrelevant', 'failed'
    fetched_at = Column(DateTime(timezone=True), server_default=func.now())

    channel = relationship("YouTubeChannel", back_populates="videos")
    transcript = relationship("VideoTranscript", back_populates="video", uselist=False) # One-to-one (or one per lang)
    analysis = relationship("VideoFeedbackAnalysis", back_populates="video", uselist=False) # One-to-one

class VideoTranscript(Base):
    """Stores the transcript for a YouTube video"""
    __tablename__ = 'video_transcripts'

    video_id = Column(String(20), ForeignKey('youtube_videos.id'), primary_key=True)
    language = Column(String(10), primary_key=True, default='en') # Assuming English for now
    transcript_text = Column(Text, nullable=True)
    fetched_at = Column(DateTime(timezone=True), server_default=func.now())

    video = relationship("YouTubeVideo", back_populates="transcript")

class VideoFeedbackAnalysis(Base):
    """Stores the structured LLM analysis of a video transcript"""
    __tablename__ = 'video_feedback_analysis'

    video_id = Column(String(20), ForeignKey('youtube_videos.id'), primary_key=True)
    llm_analysis_model = Column(String(50), nullable=True)
    llm_analysis_timestamp = Column(DateTime(timezone=True), server_default=func.now())
    summary = Column(Text, nullable=True)
    is_relevant = Column(Boolean, nullable=True) # Was the video relevant to the tracked game?
    analyzed_sentiment = Column(String(20), nullable=True)
    positive_themes = Column(ARRAY(PG_TEXT), nullable=True)
    negative_themes = Column(ARRAY(PG_TEXT), nullable=True)
    bug_reports = Column(ARRAY(PG_TEXT), nullable=True)
    feature_requests = Column(ARRAY(PG_TEXT), nullable=True)
    balance_feedback = Column(ARRAY(PG_TEXT), nullable=True)
    gameplay_loop_feedback = Column(ARRAY(PG_TEXT), nullable=True)
    monetization_feedback = Column(ARRAY(PG_TEXT), nullable=True)

    video = relationship("YouTubeVideo", back_populates="analysis") 