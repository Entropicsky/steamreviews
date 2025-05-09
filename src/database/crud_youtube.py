# src/database/crud_youtube.py
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone

from sqlalchemy.orm import Session, joinedload, aliased
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from sqlalchemy import func, update, select, desc, or_

from .models import Game, Influencer, YouTubeChannel, GameInfluencerMapping, YouTubeVideo, VideoTranscript, VideoFeedbackAnalysis

logger = logging.getLogger(__name__)

# === Game CRUD ===

def add_game(db: Session, name: str, steam_app_id: Optional[int] = None, slack_channel_id: Optional[str] = None) -> Optional[Game]:
    try:
        game = Game(name=name, steam_app_id=steam_app_id, slack_channel_id=slack_channel_id)
        db.add(game)
        db.commit()
        db.refresh(game)
        logger.info(f"Added new game: {name} (ID: {game.id})")
        return game
    except IntegrityError:
        db.rollback()
        logger.warning(f"Game with name '{name}' or Steam App ID '{steam_app_id}' already exists.")
        return db.query(Game).filter(Game.name == name).first()
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error adding game {name}: {e}", exc_info=True)
        return None

def get_game_by_id(db: Session, game_id: int) -> Optional[Game]:
    return db.query(Game).filter(Game.id == game_id).first()

def get_active_games(db: Session) -> List[Game]:
    return db.query(Game).filter(Game.is_active == True).all()

# === Influencer CRUD ===

def add_influencer(db: Session, name: str, notes: Optional[str] = None) -> Optional[Influencer]:
    try:
        influencer = Influencer(name=name, notes=notes)
        db.add(influencer)
        db.commit()
        db.refresh(influencer)
        logger.info(f"Added new influencer: {name} (ID: {influencer.id})")
        return influencer
    except IntegrityError:
        db.rollback()
        logger.warning(f"Influencer with name '{name}' already exists.")
        return db.query(Influencer).filter(Influencer.name == name).first()
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error adding influencer {name}: {e}", exc_info=True)
        return None

def get_influencer_by_id(db: Session, influencer_id: int) -> Optional[Influencer]:
    return db.query(Influencer).filter(Influencer.id == influencer_id).first()

# === YouTubeChannel CRUD ===

def add_or_update_channel(db: Session, channel_id: str, influencer_id: int, channel_name: Optional[str] = None, handle: Optional[str] = None) -> Optional[YouTubeChannel]:
    try:
        channel = db.query(YouTubeChannel).filter(YouTubeChannel.id == channel_id).first()
        if channel:
            # Update existing channel
            channel.influencer_id = influencer_id # Ensure link is correct
            if channel_name: channel.channel_name = channel_name
            if handle: channel.handle = handle
            # channel.updated_at = datetime.utcnow() # Handled by onupdate=func.now()
            logger.info(f"Updating existing channel: {channel_id}")
        else:
            # Add new channel
            channel = YouTubeChannel(
                id=channel_id,
                influencer_id=influencer_id,
                channel_name=channel_name,
                handle=handle
            )
            db.add(channel)
            logger.info(f"Adding new channel: {channel_id} for influencer {influencer_id}")
        
        db.commit()
        db.refresh(channel)
        return channel
    except IntegrityError as e:
         db.rollback()
         logger.warning(f"Integrity error adding/updating channel {channel_id} (e.g., handle conflict?): {e}")
         # Try refetching in case of race condition or existing handle
         return db.query(YouTubeChannel).filter(YouTubeChannel.id == channel_id).first()
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error adding/updating channel {channel_id}: {e}", exc_info=True)
        return None

def get_channel_by_id(db: Session, channel_id: str) -> Optional[YouTubeChannel]:
    return db.query(YouTubeChannel).filter(YouTubeChannel.id == channel_id).first()

def get_channels_by_influencer_id(db: Session, influencer_id: int) -> List[YouTubeChannel]:
    """Gets all YouTube channels associated with a specific influencer ID."""
    return db.query(YouTubeChannel).filter(YouTubeChannel.influencer_id == influencer_id).order_by(YouTubeChannel.channel_name).all()

def update_channel_timestamp(db: Session, channel_id: str, timestamp: int) -> bool:
    try:
        result = db.execute(
            update(YouTubeChannel)
            .where(YouTubeChannel.id == channel_id)
            .values(last_checked_timestamp=timestamp)
        )
        db.commit()
        if result.rowcount > 0:
             logger.debug(f"Updated last_checked_timestamp for channel {channel_id} to {timestamp}")
             return True
        else:
             logger.warning(f"Attempted to update timestamp for non-existent channel {channel_id}")
             return False
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error updating timestamp for channel {channel_id}: {e}", exc_info=True)
        return False

# === GameInfluencerMapping CRUD ===

def add_game_influencer_mapping(db: Session, game_id: int, influencer_id: int, is_active: bool = True) -> Optional[GameInfluencerMapping]:
    try:
        mapping = GameInfluencerMapping(game_id=game_id, influencer_id=influencer_id, is_active=is_active)
        db.add(mapping)
        db.commit()
        db.refresh(mapping)
        logger.info(f"Added mapping for Game ID: {game_id} and Influencer ID: {influencer_id}")
        return mapping
    except IntegrityError:
        db.rollback()
        logger.warning(f"Mapping for Game ID {game_id} and Influencer ID {influencer_id} already exists.")
        return db.query(GameInfluencerMapping).filter_by(game_id=game_id, influencer_id=influencer_id).first()
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error adding game-influencer mapping: {e}", exc_info=True)
        return None

def get_active_game_influencer_mappings(db: Session) -> List[GameInfluencerMapping]:
    """Gets all active mappings, intended for the fetcher. Relationships should be loaded by the caller if needed."""
    # Simplified query - remove complex options for now to fix syntax error
    # Fetcher will need to access mapping.game, mapping.influencer, influencer.channels
    # SQLAlchemy lazy loading will handle this by default, but can be optimized later if needed.
    return (
        db.query(GameInfluencerMapping)
        .join(GameInfluencerMapping.game)
        .join(GameInfluencerMapping.influencer)
        # Removed .join(Influencer.channels) as it's not strictly needed to find the mapping itself
        # The relationship mapping.influencer.channels can be accessed later via lazy loading.
        .filter(GameInfluencerMapping.is_active == True, Game.is_active == True)
        .all()
    )

def get_all_game_influencer_mappings(db: Session) -> List[GameInfluencerMapping]:
    """Gets all game-influencer mappings, regardless of active status, joining Game and Influencer."""
    return (
        db.query(GameInfluencerMapping)
        .join(GameInfluencerMapping.game)
        .join(GameInfluencerMapping.influencer)
        .options(
            # Eagerly load Game and Influencer names/IDs to avoid separate queries per row
            # when accessing mapping.game.name etc. later
            joinedload(GameInfluencerMapping.game),
            joinedload(GameInfluencerMapping.influencer)
        )
        .order_by(Game.name, Influencer.name)
        .all()
    )

def update_mapping_active_status(db: Session, game_id: int, influencer_id: int, is_active: bool) -> bool:
    """Updates the is_active status for a specific game-influencer mapping."""
    try:
        result = db.execute(
            update(GameInfluencerMapping)
            .where(GameInfluencerMapping.game_id == game_id, GameInfluencerMapping.influencer_id == influencer_id)
            .values(is_active=is_active)
        )
        db.commit()
        if result.rowcount > 0:
            logger.info(f"Updated active status for mapping ({game_id}, {influencer_id}) to {is_active}")
            return True
        else:
            logger.warning(f"No mapping found for ({game_id}, {influencer_id}) to update status.")
            return False
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error updating mapping status for ({game_id}, {influencer_id}): {e}", exc_info=True)
        return False

# === YouTubeVideo CRUD ===

def add_video(db: Session, video_id: str, channel_id: str, title: Optional[str], description: Optional[str], upload_date: Optional[datetime]) -> Optional[YouTubeVideo]:
    try:
        video = YouTubeVideo(
            id=video_id,
            channel_id=channel_id,
            title=title,
            description=description,
            upload_date=upload_date,
            transcript_status='pending',
            analysis_status='pending'
        )
        db.add(video)
        db.commit()
        db.refresh(video)
        logger.debug(f"Added new video record: {video_id}")
        return video
    except IntegrityError:
        db.rollback()
        logger.warning(f"Video with ID {video_id} already exists.")
        return db.query(YouTubeVideo).filter(YouTubeVideo.id == video_id).first()
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error adding video {video_id}: {e}", exc_info=True)
        return None

def get_video_by_id(db: Session, video_id: str) -> Optional[YouTubeVideo]:
    return db.query(YouTubeVideo).filter(YouTubeVideo.id == video_id).first()

def get_latest_video_upload_timestamp_for_channel(db: Session, channel_id: str) -> Optional[int]:
    """
    Gets the Unix timestamp of the most recent video upload date for a given channel.
    Returns None if no videos are found for the channel.
    """
    latest_video_date = db.query(func.max(YouTubeVideo.upload_date)).filter(YouTubeVideo.channel_id == channel_id).scalar()
    if latest_video_date:
        # Assuming upload_date is stored as a timezone-aware datetime object
        return int(latest_video_date.timestamp())
    return None

def update_video_transcript_status(db: Session, video_id: str, status: str) -> bool:
    try:
        result = db.execute(
            update(YouTubeVideo)
            .where(YouTubeVideo.id == video_id)
            .values(transcript_status=status)
        )
        db.commit()
        return result.rowcount > 0
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error updating transcript status for video {video_id}: {e}", exc_info=True)
        return False

def update_video_analysis_status(db: Session, video_id: str, status: str) -> bool:
    try:
        result = db.execute(
            update(YouTubeVideo)
            .where(YouTubeVideo.id == video_id)
            .values(analysis_status=status)
        )
        db.commit()
        return result.rowcount > 0
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error updating analysis status for video {video_id}: {e}", exc_info=True)
        return False

def get_videos_for_analysis(db: Session, limit: int = 50) -> List[YouTubeVideo]:
    """Get videos that have a transcript but haven't been analyzed yet."""
    return (
        db.query(YouTubeVideo)
        .join(VideoTranscript, YouTubeVideo.id == VideoTranscript.video_id) # Ensure transcript exists
        .filter(
            YouTubeVideo.transcript_status == 'fetched',
            YouTubeVideo.analysis_status == 'pending'
        )
        .limit(limit)
        .all()
    )

# === VideoTranscript CRUD ===

def add_transcript(db: Session, video_id: str, language: str, transcript_text: str) -> Optional[VideoTranscript]:
    try:
        transcript = VideoTranscript(
            video_id=video_id,
            language=language,
            transcript_text=transcript_text
        )
        db.add(transcript)
        db.commit()
        db.refresh(transcript)
        logger.debug(f"Added transcript for video {video_id} (lang: {language})")
        # Update the video status as well
        update_video_transcript_status(db, video_id, 'fetched')
        return transcript
    except IntegrityError:
        db.rollback()
        logger.warning(f"Transcript for video {video_id} (lang: {language}) already exists.")
        return db.query(VideoTranscript).filter_by(video_id=video_id, language=language).first()
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error adding transcript for video {video_id}: {e}", exc_info=True)
        # Reset video status if transcript add failed?
        update_video_transcript_status(db, video_id, 'failed')
        return None

def get_transcript(db: Session, video_id: str, language: str = 'en') -> Optional[VideoTranscript]:
    return db.query(VideoTranscript).filter_by(video_id=video_id, language=language).first()

# === VideoFeedbackAnalysis CRUD ===

def add_or_update_analysis(db: Session, video_id: str, analysis_data: Dict[str, Any]) -> Optional[VideoFeedbackAnalysis]:
    try:
        analysis = db.query(VideoFeedbackAnalysis).filter_by(video_id=video_id).first()
        status_to_set = 'analyzed' if analysis_data.get('is_relevant', False) else 'irrelevant'
        
        if analysis:
            # Update existing analysis
            for key, value in analysis_data.items():
                setattr(analysis, key, value)
            # analysis.llm_analysis_timestamp = datetime.utcnow() # Handled by server_default=func.now()
            logger.info(f"Updating analysis for video {video_id}")
        else:
             # Create new analysis
            analysis = VideoFeedbackAnalysis(
                video_id=video_id,
                **analysis_data # Unpack dict directly into model fields
            )
            db.add(analysis)
            logger.info(f"Adding new analysis for video {video_id}")
        
        db.commit()
        db.refresh(analysis)
        # Update the video status
        update_video_analysis_status(db, video_id, status_to_set)
        return analysis

    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error adding/updating analysis for video {video_id}: {e}", exc_info=True)
        update_video_analysis_status(db, video_id, 'failed')
        return None

def get_analysis(db: Session, video_id: str) -> Optional[VideoFeedbackAnalysis]:
    return db.query(VideoFeedbackAnalysis).filter_by(video_id=video_id).first()

def get_analyzed_feedback_for_game(db: Session, game_id: int, start_date: datetime, end_date: datetime) -> List[Dict[str, Any]]:
    """Fetches analyzed feedback details for a game within a date range, joining relevant tables."""
    results = (
        db.query(
            YouTubeVideo.id.label('video_id'),
            YouTubeVideo.title.label('video_title'),
            YouTubeVideo.upload_date.label('video_upload_date'),
            YouTubeChannel.channel_name.label('channel_name'),
            YouTubeChannel.handle.label('channel_handle'),
            Influencer.name.label('influencer_name'),
            VideoFeedbackAnalysis.summary,
            VideoFeedbackAnalysis.analyzed_sentiment,
            VideoFeedbackAnalysis.positive_themes,
            VideoFeedbackAnalysis.negative_themes,
            VideoFeedbackAnalysis.bug_reports,
            VideoFeedbackAnalysis.feature_requests,
            VideoFeedbackAnalysis.balance_feedback,
            VideoFeedbackAnalysis.gameplay_loop_feedback,
            VideoFeedbackAnalysis.monetization_feedback,
            VideoFeedbackAnalysis.llm_analysis_timestamp
        )
        .join(VideoFeedbackAnalysis, YouTubeVideo.id == VideoFeedbackAnalysis.video_id)
        .join(YouTubeChannel, YouTubeVideo.channel_id == YouTubeChannel.id)
        .join(Influencer, YouTubeChannel.influencer_id == Influencer.id)
        .join(GameInfluencerMapping, Influencer.id == GameInfluencerMapping.influencer_id)
        .filter(
            GameInfluencerMapping.game_id == game_id,
            VideoFeedbackAnalysis.is_relevant == True, # Only show relevant videos
            YouTubeVideo.upload_date >= start_date,
            YouTubeVideo.upload_date < end_date
        )
        .order_by(YouTubeVideo.upload_date.desc())
        .all()
    )
    # Convert results to list of dictionaries
    return [row._asdict() for row in results] 