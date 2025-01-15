"""add social memory

Revision ID: 9e791cda742d
Revises: 5c665a534773
Create Date: 2025-01-15 09:57:30.399510

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '9e791cda742d'
down_revision: Union[str, None] = '5c665a534773'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create social_memory table
    op.create_table(
        'social_memory',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('character_name', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('platform', sa.String(), nullable=False),
        sa.Column('last_interaction', sa.DateTime(timezone=True), nullable=True),
        sa.Column('interaction_count', sa.Integer(), nullable=True, default=0),
        sa.Column('opinion', sa.String(), nullable=True),
        sa.Column('conversation_history', sa.JSON(), nullable=True),
        sa.Column('last_processed_message_id', sa.String(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

    # Add indexes for common queries
    op.create_index(
        'ix_social_memory_character_user_platform',
        'social_memory',
        ['character_name', 'user_id', 'platform'],
        unique=True
    )
    op.create_index(
        'ix_social_memory_last_interaction',
        'social_memory',
        ['last_interaction']
    )


def downgrade() -> None:
    # Drop indexes
    op.drop_index('ix_social_memory_last_interaction')
    op.drop_index('ix_social_memory_character_user_platform')
    
    # Drop table
    op.drop_table('social_memory')