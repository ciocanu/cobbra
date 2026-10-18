"""add_ai_usage_and_demo_flag

Revision ID: c7d2e4f1a903
Revises: b3f1a2c8d901
Create Date: 2026-10-18

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'c7d2e4f1a903'
down_revision: Union[str, Sequence[str], None] = 'b3f1a2c8d901'
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())

    if 'is_demo' not in {c['name'] for c in inspector.get_columns('users')}:
        op.add_column('users', sa.Column('is_demo', sa.Boolean(), nullable=False, server_default=sa.false()))

    if not inspector.has_table('ai_usage'):
        op.create_table(
            'ai_usage',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
            sa.Column('feature', sa.String(), nullable=False),
            sa.Column('model', sa.String(), nullable=False),
            sa.Column('input_tokens', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('output_tokens', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('cost_usd', sa.Float(), nullable=False, server_default='0'),
            sa.Column('created_at', sa.DateTime(), nullable=False),
        )
        op.create_index('ix_ai_usage_user_id', 'ai_usage', ['user_id'])
        op.create_index('ix_ai_usage_created_at', 'ai_usage', ['created_at'])


def downgrade() -> None:
    op.drop_index('ix_ai_usage_created_at', table_name='ai_usage')
    op.drop_index('ix_ai_usage_user_id', table_name='ai_usage')
    op.drop_table('ai_usage')
    op.drop_column('users', 'is_demo')
