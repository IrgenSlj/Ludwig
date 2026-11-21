"""Baseline: the schema as created before migrations (projects, uploads, runs, findings,
reviews, limit changes)."""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None


def upgrade() -> None:
    op.create_table(
        "project",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("created", sa.DateTime, nullable=False),
    )
    op.create_table(
        "upload",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("project_id", sa.Integer, sa.ForeignKey("project.id"), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("size", sa.Integer, nullable=False),
        sa.Column("for_upload_id", sa.Integer, sa.ForeignKey("upload.id")),
        sa.Column("created", sa.DateTime, nullable=False),
    )
    op.create_index("ix_upload_project_id", "upload", ["project_id"])
    op.create_table(
        "run",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("project_id", sa.Integer, sa.ForeignKey("project.id"), nullable=False),
        sa.Column("pack_name", sa.String(100), nullable=False),
        sa.Column("pack_version", sa.String(50), nullable=False),
        sa.Column("pack_hash", sa.String(80), nullable=False),
        sa.Column("upload_ids", sa.JSON, nullable=False),
        sa.Column("upload_hashes", sa.JSON, nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("error", sa.Text),
        sa.Column("summary", sa.JSON),
        sa.Column("created", sa.DateTime, nullable=False),
        sa.Column("finished", sa.DateTime),
        sa.Column("files", sa.JSON),
    )
    op.create_index("ix_run_project_id", "run", ["project_id"])
    op.create_table(
        "finding",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("run_id", sa.Integer, sa.ForeignKey("run.id"), nullable=False),
        sa.Column("position", sa.Integer, nullable=False),
        sa.Column("rule_id", sa.String(120), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("mark", sa.String(100)),
        sa.Column("data", sa.JSON, nullable=False),
    )
    op.create_index("ix_finding_run_id", "finding", ["run_id"])
    op.create_index("ix_finding_status", "finding", ["status"])
    op.create_table(
        "review",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("finding_id", sa.Integer, sa.ForeignKey("finding.id"), nullable=False),
        sa.Column("decision", sa.String(20), nullable=False),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("created", sa.DateTime, nullable=False),
    )
    op.create_index("ix_review_finding_id", "review", ["finding_id"])
    op.create_table(
        "limit_change",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("pack_name", sa.String(100), nullable=False),
        sa.Column("values", sa.JSON, nullable=False),
        sa.Column("old_sha256", sa.String(64), nullable=False),
        sa.Column("new_sha256", sa.String(64), nullable=False),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("created", sa.DateTime, nullable=False),
    )
    op.create_index("ix_limit_change_pack_name", "limit_change", ["pack_name"])
