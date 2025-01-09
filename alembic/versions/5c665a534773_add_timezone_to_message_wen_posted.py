"""Add timezone to message.wen_posted

Revision ID: 5c665a534773
Revises: ac438a8b7806
Create Date: 2025-01-09 11:49:16.089866

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '5c665a534773'
down_revision: Union[str, None] = 'ac438a8b7806'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.alter_column('message', 'wen_posted',
               existing_type=sa.DateTime(),
               type_=sa.DateTime(timezone=True),
               existing_nullable=True)


def downgrade():
    op.alter_column('message', 'wen_posted',
               existing_type=sa.DateTime(timezone=True),
               type_=sa.DateTime(),
               existing_nullable=True)
