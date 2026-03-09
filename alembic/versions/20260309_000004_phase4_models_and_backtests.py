"""Add Phase 4 model registry, validation, and backtest tables."""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260309_000004"
down_revision = "20260309_000003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "model_training_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("dataset_snapshot_id", sa.Integer(), nullable=True),
        sa.Column("model_family", sa.String(length=64), nullable=False),
        sa.Column("model_version", sa.String(length=128), nullable=True),
        sa.Column("summary_json", sa.Text(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["dataset_snapshot_id"], ["dataset_snapshots.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_model_training_runs_status",
        "model_training_runs",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_model_training_runs_as_of_date",
        "model_training_runs",
        ["as_of_date"],
        unique=False,
    )
    op.create_index(
        "ix_model_training_runs_created_at",
        "model_training_runs",
        ["created_at"],
        unique=False,
    )

    op.create_table(
        "model_registry_entries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("version", sa.String(length=128), nullable=False),
        sa.Column("family", sa.String(length=64), nullable=False),
        sa.Column("dataset_snapshot_id", sa.Integer(), nullable=False),
        sa.Column("feature_set_version", sa.String(length=64), nullable=False),
        sa.Column("label_version", sa.String(length=64), nullable=False),
        sa.Column("training_start_date", sa.Date(), nullable=False),
        sa.Column("training_end_date", sa.Date(), nullable=False),
        sa.Column("training_row_count", sa.Integer(), nullable=False),
        sa.Column("artifact_path", sa.Text(), nullable=False),
        sa.Column("metrics_json", sa.Text(), nullable=False),
        sa.Column("benchmark_metrics_json", sa.Text(), nullable=False),
        sa.Column("promotion_status", sa.String(length=32), nullable=False),
        sa.Column("promotion_reasons_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["dataset_snapshot_id"], ["dataset_snapshots.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("version"),
    )
    op.create_index(
        "ix_model_registry_entries_version",
        "model_registry_entries",
        ["version"],
        unique=True,
    )
    op.create_index(
        "ix_model_registry_entries_family",
        "model_registry_entries",
        ["family"],
        unique=False,
    )
    op.create_index(
        "ix_model_registry_entries_promotion_status",
        "model_registry_entries",
        ["promotion_status"],
        unique=False,
    )
    op.create_index(
        "ix_model_registry_entries_created_at",
        "model_registry_entries",
        ["created_at"],
        unique=False,
    )

    op.create_table(
        "validation_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("dataset_snapshot_id", sa.Integer(), nullable=False),
        sa.Column("model_entry_id", sa.Integer(), nullable=True),
        sa.Column("fold_count", sa.Integer(), nullable=False),
        sa.Column("artifact_path", sa.Text(), nullable=True),
        sa.Column("summary_json", sa.Text(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["dataset_snapshot_id"], ["dataset_snapshots.id"]),
        sa.ForeignKeyConstraint(["model_entry_id"], ["model_registry_entries.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_validation_runs_status", "validation_runs", ["status"], unique=False)
    op.create_index(
        "ix_validation_runs_created_at",
        "validation_runs",
        ["created_at"],
        unique=False,
    )

    op.create_table(
        "backtest_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("mode", sa.String(length=32), nullable=False),
        sa.Column("dataset_snapshot_id", sa.Integer(), nullable=False),
        sa.Column("model_entry_id", sa.Integer(), nullable=True),
        sa.Column("benchmark_symbol", sa.String(length=32), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("artifact_path", sa.Text(), nullable=True),
        sa.Column("summary_json", sa.Text(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["dataset_snapshot_id"], ["dataset_snapshots.id"]),
        sa.ForeignKeyConstraint(["model_entry_id"], ["model_registry_entries.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_backtest_runs_status", "backtest_runs", ["status"], unique=False)
    op.create_index("ix_backtest_runs_mode", "backtest_runs", ["mode"], unique=False)
    op.create_index(
        "ix_backtest_runs_start_date",
        "backtest_runs",
        ["start_date"],
        unique=False,
    )
    op.create_index(
        "ix_backtest_runs_end_date",
        "backtest_runs",
        ["end_date"],
        unique=False,
    )
    op.create_index(
        "ix_backtest_runs_created_at",
        "backtest_runs",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_backtest_runs_created_at", table_name="backtest_runs")
    op.drop_index("ix_backtest_runs_end_date", table_name="backtest_runs")
    op.drop_index("ix_backtest_runs_start_date", table_name="backtest_runs")
    op.drop_index("ix_backtest_runs_mode", table_name="backtest_runs")
    op.drop_index("ix_backtest_runs_status", table_name="backtest_runs")
    op.drop_table("backtest_runs")
    op.drop_index("ix_validation_runs_created_at", table_name="validation_runs")
    op.drop_index("ix_validation_runs_status", table_name="validation_runs")
    op.drop_table("validation_runs")
    op.drop_index(
        "ix_model_registry_entries_created_at",
        table_name="model_registry_entries",
    )
    op.drop_index(
        "ix_model_registry_entries_promotion_status",
        table_name="model_registry_entries",
    )
    op.drop_index("ix_model_registry_entries_family", table_name="model_registry_entries")
    op.drop_index("ix_model_registry_entries_version", table_name="model_registry_entries")
    op.drop_table("model_registry_entries")
    op.drop_index("ix_model_training_runs_created_at", table_name="model_training_runs")
    op.drop_index("ix_model_training_runs_as_of_date", table_name="model_training_runs")
    op.drop_index("ix_model_training_runs_status", table_name="model_training_runs")
    op.drop_table("model_training_runs")
