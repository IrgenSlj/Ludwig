"""Pilot: personal logins, sessions, activity log, and who made each review and limit change."""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"


def upgrade() -> None:
    op.create_table(
        "app_user",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(300), nullable=False),
        sa.Column("is_admin", sa.Boolean, nullable=False),
        sa.Column("active", sa.Boolean, nullable=False),
        sa.Column("created", sa.DateTime, nullable=False),
    )
    op.create_table(
        "user_session",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("app_user.id"), nullable=False),
        sa.Column("created", sa.DateTime, nullable=False),
        sa.Column("expires", sa.DateTime, nullable=False),
    )
    op.create_index("ix_user_session_user_id", "user_session", ["user_id"])
    op.create_table(
        "event",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("created", sa.DateTime, nullable=False),
        sa.Column("user_name", sa.String(100)),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("project_id", sa.Integer),
        sa.Column("detail", sa.JSON, nullable=False),
    )
    op.create_index("ix_event_created", "event", ["created"])
    op.create_index("ix_event_project_id", "event", ["project_id"])
    with op.batch_alter_table("review") as batch:
        batch.add_column(sa.Column("user_name", sa.String(100)))
    with op.batch_alter_table("limit_change") as batch:
        batch.add_column(sa.Column("user_name", sa.String(100)))
