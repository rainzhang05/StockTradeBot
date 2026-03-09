"""Add Phase 9 intraday research tables and frequency metadata."""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260309_000007"
down_revision = "20260309_000006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "backfill_runs",
        sa.Column("domain", sa.String(length=32), nullable=False, server_default="daily"),
    )
    op.add_column(
        "backfill_runs",
        sa.Column("frequency", sa.String(length=16), nullable=True),
    )
    op.create_index("ix_backfill_runs_domain", "backfill_runs", ["domain"], unique=False)
    op.create_index("ix_backfill_runs_frequency", "backfill_runs", ["frequency"], unique=False)

    op.create_table(
        "intraday_bar_observations",
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("frequency", sa.String(length=16), nullable=False),
        sa.Column("bar_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("session_date", sa.Date(), nullable=False),
        sa.Column("open", sa.Float(), nullable=False),
        sa.Column("high", sa.Float(), nullable=False),
        sa.Column("low", sa.Float(), nullable=False),
        sa.Column("close", sa.Float(), nullable=False),
        sa.Column("volume", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("split_adjusted", sa.Boolean(), nullable=False),
        sa.Column("payload_id", sa.Integer(), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["payload_id"], ["provider_payloads.id"]),
        sa.PrimaryKeyConstraint("provider", "symbol", "frequency", "bar_start"),
    )
    op.create_index(
        "ix_intraday_bar_observations_symbol", "intraday_bar_observations", ["symbol"], unique=False
    )
    op.create_index(
        "ix_intraday_bar_observations_frequency",
        "intraday_bar_observations",
        ["frequency"],
        unique=False,
    )
    op.create_index(
        "ix_intraday_bar_observations_bar_start",
        "intraday_bar_observations",
        ["bar_start"],
        unique=False,
    )
    op.create_index(
        "ix_intraday_bar_observations_session_date",
        "intraday_bar_observations",
        ["session_date"],
        unique=False,
    )

    op.create_table(
        "canonical_intraday_bars",
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("frequency", sa.String(length=16), nullable=False),
        sa.Column("bar_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("session_date", sa.Date(), nullable=False),
        sa.Column("open", sa.Float(), nullable=False),
        sa.Column("high", sa.Float(), nullable=False),
        sa.Column("low", sa.Float(), nullable=False),
        sa.Column("close", sa.Float(), nullable=False),
        sa.Column("volume", sa.BigInteger(), nullable=False),
        sa.Column("validation_tier", sa.String(length=20), nullable=False),
        sa.Column("primary_provider", sa.String(length=50), nullable=False),
        sa.Column("confirming_provider", sa.String(length=50), nullable=True),
        sa.Column("field_provenance", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("symbol", "frequency", "bar_start"),
    )
    op.create_index(
        "ix_canonical_intraday_bars_frequency",
        "canonical_intraday_bars",
        ["frequency"],
        unique=False,
    )
    op.create_index(
        "ix_canonical_intraday_bars_bar_start",
        "canonical_intraday_bars",
        ["bar_start"],
        unique=False,
    )
    op.create_index(
        "ix_canonical_intraday_bars_session_date",
        "canonical_intraday_bars",
        ["session_date"],
        unique=False,
    )
    op.create_index(
        "ix_canonical_intraday_bars_validation_tier",
        "canonical_intraday_bars",
        ["validation_tier"],
        unique=False,
    )

    op.add_column(
        "dataset_snapshots",
        sa.Column("as_of_timestamp", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "dataset_snapshots",
        sa.Column("frequency", sa.String(length=16), nullable=False, server_default="daily"),
    )
    op.create_index(
        "ix_dataset_snapshots_as_of_timestamp",
        "dataset_snapshots",
        ["as_of_timestamp"],
        unique=False,
    )
    op.create_index(
        "ix_dataset_snapshots_frequency", "dataset_snapshots", ["frequency"], unique=False
    )

    op.add_column(
        "model_training_runs",
        sa.Column("frequency", sa.String(length=16), nullable=False, server_default="daily"),
    )
    op.create_index(
        "ix_model_training_runs_frequency", "model_training_runs", ["frequency"], unique=False
    )

    op.add_column(
        "model_registry_entries",
        sa.Column("frequency", sa.String(length=16), nullable=False, server_default="daily"),
    )
    op.create_index(
        "ix_model_registry_entries_frequency", "model_registry_entries", ["frequency"], unique=False
    )

    op.add_column(
        "validation_runs",
        sa.Column("frequency", sa.String(length=16), nullable=False, server_default="daily"),
    )
    op.create_index("ix_validation_runs_frequency", "validation_runs", ["frequency"], unique=False)

    op.add_column(
        "backtest_runs",
        sa.Column("frequency", sa.String(length=16), nullable=False, server_default="daily"),
    )
    op.create_index("ix_backtest_runs_frequency", "backtest_runs", ["frequency"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_backtest_runs_frequency", table_name="backtest_runs")
    op.drop_column("backtest_runs", "frequency")

    op.drop_index("ix_validation_runs_frequency", table_name="validation_runs")
    op.drop_column("validation_runs", "frequency")

    op.drop_index("ix_model_registry_entries_frequency", table_name="model_registry_entries")
    op.drop_column("model_registry_entries", "frequency")

    op.drop_index("ix_model_training_runs_frequency", table_name="model_training_runs")
    op.drop_column("model_training_runs", "frequency")

    op.drop_index("ix_dataset_snapshots_frequency", table_name="dataset_snapshots")
    op.drop_index("ix_dataset_snapshots_as_of_timestamp", table_name="dataset_snapshots")
    op.drop_column("dataset_snapshots", "frequency")
    op.drop_column("dataset_snapshots", "as_of_timestamp")

    op.drop_index(
        "ix_canonical_intraday_bars_validation_tier", table_name="canonical_intraday_bars"
    )
    op.drop_index("ix_canonical_intraday_bars_session_date", table_name="canonical_intraday_bars")
    op.drop_index("ix_canonical_intraday_bars_bar_start", table_name="canonical_intraday_bars")
    op.drop_index("ix_canonical_intraday_bars_frequency", table_name="canonical_intraday_bars")
    op.drop_table("canonical_intraday_bars")

    op.drop_index(
        "ix_intraday_bar_observations_session_date", table_name="intraday_bar_observations"
    )
    op.drop_index("ix_intraday_bar_observations_bar_start", table_name="intraday_bar_observations")
    op.drop_index("ix_intraday_bar_observations_frequency", table_name="intraday_bar_observations")
    op.drop_index("ix_intraday_bar_observations_symbol", table_name="intraday_bar_observations")
    op.drop_table("intraday_bar_observations")

    op.drop_index("ix_backfill_runs_frequency", table_name="backfill_runs")
    op.drop_index("ix_backfill_runs_domain", table_name="backfill_runs")
    op.drop_column("backfill_runs", "frequency")
    op.drop_column("backfill_runs", "domain")
