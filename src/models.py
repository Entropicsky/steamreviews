from dataclasses import dataclass, asdict, field
from typing import Optional, Dict, Any, List
from datetime import datetime
from pydantic import BaseModel, Field

@dataclass
class Author:
    """Represents the author of a Steam review."""
    steamid: str
    num_games_owned: int = 0
    num_reviews: int = 0
    playtime_forever: int = 0
    playtime_last_two_weeks: int = 0
    playtime_at_review: int = 0
    last_played: int = 0 # Timestamp

@dataclass
class Review:
    """Data class for storing Steam review information."""
    recommendationid: str
    appid: str
    author: Author # Embed the Author dataclass
    language: str
    review_text: str = field(repr=False) # Don't show full text in default repr
    timestamp_created: int
    timestamp_updated: int
    voted_up: bool
    votes_up: int = 0
    votes_funny: int = 0
    weighted_vote_score: float = 0.0
    comment_count: int = 0
    steam_purchase: bool = False
    received_for_free: bool = False
    written_during_early_access: bool = False
    developer_response: Optional[str] = field(default=None, repr=False) # Don't show full response
    timestamp_dev_responded: Optional[int] = None
    translated_text: Optional[str] = field(default=None, repr=False) # Don't show full translation

    # Properties from the old version (can be kept or removed based on preference)
    @property
    def created_date(self) -> str:
        """Return the formatted creation date."""
        return datetime.fromtimestamp(self.timestamp_created).strftime('%Y-%m-%d')

    @property
    def sentiment(self) -> str:
        """Return the sentiment (positive/negative)."""
        return "Positive" if self.voted_up else "Negative"

    def to_dict(self) -> Dict[str, Any]:
        """Convert Review and nested Author to dictionary."""
        return asdict(self)

# --- Pydantic Model for Structured Analysis Output ---
class AnalysisResponse(BaseModel):
    """Pydantic model for the structured analysis response from OpenAI."""
    overall_sentiment: str = Field(description="Brief summary text of overall sentiment")
    positive_themes: List[str] = Field(default_factory=list, description="List of key positive themes mentioned")
    negative_themes: List[str] = Field(default_factory=list, description="List of key negative themes mentioned")
    feature_analysis: str = Field(description="Analysis of comments on specific game features/mechanics")
    player_suggestions: List[str] = Field(default_factory=list, description="List of common player suggestions or requests")
    developer_opportunities: str = Field(description="Key opportunities for the developer to improve the game")
    playtime_engagement_insights: str = Field(description="Observations about how feedback might differ based on player playtime")
    cultural_insights: Optional[str] = Field(default=None, description="Optional: Unique perspectives potentially tied to the Chinese player base") 