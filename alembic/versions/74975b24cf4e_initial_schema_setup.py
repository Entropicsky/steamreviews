"""Initial schema setup

Revision ID: 74975b24cf4e
Revises: 
Create Date: 2025-05-04 16:11:24.822248

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql # Import postgresql dialect for ARRAY type


# revision identifiers, used by Alembic.
revision: str = '74975b24cf4e'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Manually define upgrade schema."""
    op.create_table('tracked_apps',
        sa.Column('app_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=True),
        sa.Column('last_fetched_timestamp', sa.BigInteger(), nullable=True, server_default='0'),
        sa.Column('added_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=True),
        sa.PrimaryKeyConstraint('app_id')
    )
    op.create_index(op.f('ix_tracked_apps_app_id'), 'tracked_apps', ['app_id'], unique=False)

    op.create_table('reviews',
        sa.Column('recommendationid', sa.BigInteger(), nullable=False),
        sa.Column('app_id', sa.Integer(), nullable=True),
        sa.Column('author_steamid', sa.String(length=30), nullable=True),
        sa.Column('original_language', sa.String(length=20), nullable=False),
        sa.Column('original_review_text', sa.Text(), nullable=True),
        sa.Column('english_translation', sa.Text(), nullable=True),
        sa.Column('translation_status', sa.String(length=20), server_default='pending', nullable=True),
        sa.Column('translation_model', sa.String(length=50), nullable=True),
        sa.Column('analysis_status', sa.String(length=20), server_default='pending', nullable=True),
        sa.Column('analyzed_sentiment', sa.String(length=20), nullable=True),
        sa.Column('positive_themes', postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column('negative_themes', postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column('feature_requests', postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column('bug_reports', postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column('llm_analysis_model', sa.String(length=50), nullable=True),
        sa.Column('llm_analysis_timestamp', sa.DateTime(timezone=True), nullable=True),
        sa.Column('timestamp_created', sa.BigInteger(), nullable=False),
        sa.Column('timestamp_updated', sa.BigInteger(), nullable=False),
        sa.Column('voted_up', sa.Boolean(), nullable=False),
        sa.Column('votes_up', sa.Integer(), server_default='0', nullable=True),
        sa.Column('votes_funny', sa.Integer(), server_default='0', nullable=True),
        sa.Column('weighted_vote_score', sa.Numeric(precision=10, scale=9), server_default='0.0', nullable=True),
        sa.Column('comment_count', sa.Integer(), server_default='0', nullable=True),
        sa.Column('steam_purchase', sa.Boolean(), server_default=sa.text('false'), nullable=True),
        sa.Column('received_for_free', sa.Boolean(), server_default=sa.text('false'), nullable=True),
        sa.Column('written_during_early_access', sa.Boolean(), server_default=sa.text('false'), nullable=True),
        sa.Column('developer_response', sa.Text(), nullable=True),
        sa.Column('timestamp_dev_responded', sa.BigInteger(), nullable=True),
        sa.Column('author_num_games_owned', sa.Integer(), server_default='0', nullable=True),
        sa.Column('author_num_reviews', sa.Integer(), server_default='0', nullable=True),
        sa.Column('author_playtime_forever', sa.Integer(), server_default='0', nullable=True),
        sa.Column('author_playtime_last_two_weeks', sa.Integer(), server_default='0', nullable=True),
        sa.Column('author_playtime_at_review', sa.Integer(), server_default='0', nullable=True),
        sa.Column('author_last_played', sa.BigInteger(), server_default='0', nullable=True),
        sa.Column('db_inserted_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('db_last_updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['app_id'], ['tracked_apps.app_id'], ),
        sa.PrimaryKeyConstraint('recommendationid')
    )
    op.create_index(op.f('ix_reviews_analysis_status'), 'reviews', ['analysis_status'], unique=False)
    op.create_index(op.f('ix_reviews_app_id'), 'reviews', ['app_id'], unique=False)
    op.create_index(op.f('ix_reviews_original_language'), 'reviews', ['original_language'], unique=False)
    op.create_index(op.f('ix_reviews_recommendationid'), 'reviews', ['recommendationid'], unique=False)
    op.create_index(op.f('ix_reviews_timestamp_created'), 'reviews', ['timestamp_created'], unique=False)
    op.create_index(op.f('ix_reviews_translation_status'), 'reviews', ['translation_status'], unique=False)


def downgrade() -> None:
    """Manually define downgrade schema."""
    op.drop_index(op.f('ix_reviews_translation_status'), table_name='reviews')
    op.drop_index(op.f('ix_reviews_timestamp_created'), table_name='reviews')
    op.drop_index(op.f('ix_reviews_recommendationid'), table_name='reviews')
    op.drop_index(op.f('ix_reviews_original_language'), table_name='reviews')
    op.drop_index(op.f('ix_reviews_app_id'), table_name='reviews')
    op.drop_index(op.f('ix_reviews_analysis_status'), table_name='reviews')
    op.drop_table('reviews')
    op.drop_index(op.f('ix_tracked_apps_app_id'), table_name='tracked_apps')
    op.drop_table('tracked_apps')
