"""add_file_hash_to_activities

Revision ID: b3f1a2c8d901
Revises: edcd22bd7c32
Create Date: 2026-06-20

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'b3f1a2c8d901'
down_revision: Union[str, Sequence[str], None] = 'edcd22bd7c32'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('activities', sa.Column('file_hash', sa.String(), nullable=True))
    op.create_index('ix_activities_file_hash', 'activities', ['file_hash'])


def downgrade() -> None:
    op.drop_index('ix_activities_file_hash', table_name='activities')
    op.drop_column('activities', 'file_hash')
