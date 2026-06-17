"""add_fk_query_indexes

Adds indexes on the foreign-key / filter columns that are scanned on every
request, in preparation for PostgreSQL in production. On SQLite (dev) these
help too; on Postgres they turn per-user / per-activity lookups from
sequential scans into index scans.

Deliberately NOT added (already covered by an implicit UNIQUE index):
  - hydration_analyses.activity_id   (unique=True)
  - durability_analyses.activity_id  (unique=True)
  - indoor_outdoor_profiles.user_id  (unique=True)

The app builds its base schema with Base.metadata.create_all() and the models
now declare these same indexes, so on a fresh database create_all() may have
already created them. Each index is therefore created defensively: only when
the table exists and the index does not — making this migration idempotent and
independent of whether create_all() ran first.

Revision ID: edcd22bd7c32
Revises: ad8fb9458ec3
Create Date: 2026-06-17 13:55:00.000000

"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = 'edcd22bd7c32'
down_revision: Union[str, Sequence[str], None] = 'ad8fb9458ec3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (index name, table, [columns])
_INDEXES = [
    ('ix_activities_user_id_date',        'activities',       ['user_id', 'date']),
    ('ix_track_points_activity_id',       'track_points',     ['activity_id']),
    ('ix_laps_activity_id',               'laps',             ['activity_id']),
    ('ix_personal_records_user_id',       'personal_records', ['user_id']),
    ('ix_goals_user_id',                  'goals',            ['user_id']),
    ('ix_segments_user_id',               'segments',         ['user_id']),
    ('ix_segment_efforts_segment_id',     'segment_efforts',  ['segment_id']),
    ('ix_segment_efforts_activity_id',    'segment_efforts',  ['activity_id']),
    ('ix_climb_detections_activity_id',   'climb_detections', ['activity_id']),
]


def upgrade() -> None:
    """Upgrade schema."""
    inspector = inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    for name, table, columns in _INDEXES:
        if table not in tables:
            continue  # table not created yet (create_all hasn't run)
        existing = {ix['name'] for ix in inspector.get_indexes(table)}
        if name in existing:
            continue  # create_all() already made it
        op.create_index(name, table, columns)


def downgrade() -> None:
    """Downgrade schema."""
    inspector = inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    for name, table, _ in reversed(_INDEXES):
        if table not in tables:
            continue
        existing = {ix['name'] for ix in inspector.get_indexes(table)}
        if name in existing:
            op.drop_index(name, table_name=table)
