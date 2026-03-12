"""Add daily research quality scope columns."""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260312_000008"
down_revision = "20260309_000007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "dataset_snapshots",
        sa.Column(
            "quality_scope", sa.String(length=16), nullable=False, server_default="promotion"
        ),
    )
    op.add_column(
        "model_registry_entries",
        sa.Column(
            "quality_scope", sa.String(length=16), nullable=False, server_default="promotion"
        ),
    )
    op.add_column(
        "validation_runs",
        sa.Column(
            "quality_scope", sa.String(length=16), nullable=False, server_default="promotion"
        ),
    )
    op.add_column(
        "backtest_runs",
        sa.Column(
            "quality_scope", sa.String(length=16), nullable=False, server_default="promotion"
        ),
    )

    op.create_index(
        "ix_dataset_snapshots_quality_scope",
        "dataset_snapshots",
        ["quality_scope"],
        unique=False,
    )
    op.create_index(
        "ix_model_registry_entries_quality_scope",
        "model_registry_entries",
        ["quality_scope"],
        unique=False,
    )
    op.create_index(
        "ix_validation_runs_quality_scope",
        "validation_runs",
        ["quality_scope"],
        unique=False,
    )
    op.create_index(
        "ix_backtest_runs_quality_scope",
        "backtest_runs",
        ["quality_scope"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_backtest_runs_quality_scope", table_name="backtest_runs")
    op.drop_index("ix_validation_runs_quality_scope", table_name="validation_runs")
    op.drop_index(
        "ix_model_registry_entries_quality_scope",
        table_name="model_registry_entries",
    )
    op.drop_index("ix_dataset_snapshots_quality_scope", table_name="dataset_snapshots")

    op.drop_column("backtest_runs", "quality_scope")
    op.drop_column("validation_runs", "quality_scope")
    op.drop_column("model_registry_entries", "quality_scope")
    op.drop_column("dataset_snapshots", "quality_scope")
