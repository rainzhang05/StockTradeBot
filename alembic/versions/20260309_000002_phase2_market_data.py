"""Add Phase 2 market-data storage tables."""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260309_000002"
down_revision = "20260309_000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "backfill_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("requested_symbols", sa.Text(), nullable=False),
        sa.Column("primary_provider", sa.String(length=50), nullable=False),
        sa.Column("secondary_provider", sa.String(length=50), nullable=True),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("lookback_days", sa.Integer(), nullable=False),
        sa.Column("summary_json", sa.Text(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_backfill_runs_status", "backfill_runs", ["status"], unique=False)
    op.create_index("ix_backfill_runs_as_of_date", "backfill_runs", ["as_of_date"], unique=False)
    op.create_index("ix_backfill_runs_created_at", "backfill_runs", ["created_at"], unique=False)

    op.create_table(
        "provider_payloads",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("domain", sa.String(length=50), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("request_url", sa.Text(), nullable=False),
        sa.Column("payload_format", sa.String(length=16), nullable=False),
        sa.Column("payload_path", sa.Text(), nullable=False),
        sa.Column("checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column("byte_count", sa.Integer(), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("payload_path"),
    )
    op.create_index(
        "ix_provider_payloads_provider",
        "provider_payloads",
        ["provider"],
        unique=False,
    )
    op.create_index("ix_provider_payloads_domain", "provider_payloads", ["domain"], unique=False)
    op.create_index("ix_provider_payloads_symbol", "provider_payloads", ["symbol"], unique=False)
    op.create_index(
        "ix_provider_payloads_requested_at",
        "provider_payloads",
        ["requested_at"],
        unique=False,
    )

    op.create_table(
        "daily_bar_observations",
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
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
        sa.PrimaryKeyConstraint("provider", "symbol", "trade_date"),
    )
    op.create_index(
        "ix_daily_bar_observations_symbol",
        "daily_bar_observations",
        ["symbol"],
        unique=False,
    )
    op.create_index(
        "ix_daily_bar_observations_trade_date",
        "daily_bar_observations",
        ["trade_date"],
        unique=False,
    )

    op.create_table(
        "corporate_action_observations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("ex_date", sa.Date(), nullable=False),
        sa.Column("action_type", sa.String(length=32), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("payload_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["payload_id"], ["provider_payloads.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_corporate_action_observations_provider",
        "corporate_action_observations",
        ["provider"],
        unique=False,
    )
    op.create_index(
        "ix_corporate_action_observations_symbol",
        "corporate_action_observations",
        ["symbol"],
        unique=False,
    )
    op.create_index(
        "ix_corporate_action_observations_ex_date",
        "corporate_action_observations",
        ["ex_date"],
        unique=False,
    )
    op.create_index(
        "ix_corporate_action_observations_action_type",
        "corporate_action_observations",
        ["action_type"],
        unique=False,
    )

    op.create_table(
        "canonical_daily_bars",
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
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
        sa.PrimaryKeyConstraint("symbol", "trade_date"),
    )
    op.create_index(
        "ix_canonical_daily_bars_trade_date",
        "canonical_daily_bars",
        ["trade_date"],
        unique=False,
    )
    op.create_index(
        "ix_canonical_daily_bars_validation_tier",
        "canonical_daily_bars",
        ["validation_tier"],
        unique=False,
    )

    op.create_table(
        "data_quality_incidents",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("domain", sa.String(length=32), nullable=False),
        sa.Column("affected_fields", sa.Text(), nullable=False),
        sa.Column("involved_providers", sa.Text(), nullable=False),
        sa.Column("observed_values", sa.Text(), nullable=False),
        sa.Column("resolution_status", sa.String(length=20), nullable=False),
        sa.Column("operator_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_data_quality_incidents_symbol",
        "data_quality_incidents",
        ["symbol"],
        unique=False,
    )
    op.create_index(
        "ix_data_quality_incidents_trade_date",
        "data_quality_incidents",
        ["trade_date"],
        unique=False,
    )
    op.create_index(
        "ix_data_quality_incidents_domain",
        "data_quality_incidents",
        ["domain"],
        unique=False,
    )
    op.create_index(
        "ix_data_quality_incidents_resolution_status",
        "data_quality_incidents",
        ["resolution_status"],
        unique=False,
    )
    op.create_index(
        "ix_data_quality_incidents_created_at",
        "data_quality_incidents",
        ["created_at"],
        unique=False,
    )

    op.create_table(
        "universe_snapshots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("effective_date", sa.Date(), nullable=False),
        sa.Column("stock_count", sa.Integer(), nullable=False),
        sa.Column("etf_count", sa.Integer(), nullable=False),
        sa.Column("selection_version", sa.String(length=50), nullable=False),
        sa.Column("summary_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_universe_snapshots_effective_date",
        "universe_snapshots",
        ["effective_date"],
        unique=False,
    )
    op.create_index(
        "ix_universe_snapshots_created_at",
        "universe_snapshots",
        ["created_at"],
        unique=False,
    )

    op.create_table(
        "universe_snapshot_members",
        sa.Column("snapshot_id", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("asset_type", sa.String(length=16), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=True),
        sa.Column("liquidity_score", sa.Float(), nullable=True),
        sa.Column("inclusion_reason", sa.String(length=64), nullable=False),
        sa.Column("latest_validation_tier", sa.String(length=20), nullable=False),
        sa.ForeignKeyConstraint(["snapshot_id"], ["universe_snapshots.id"]),
        sa.PrimaryKeyConstraint("snapshot_id", "symbol"),
    )
    op.create_index(
        "ix_universe_snapshot_members_asset_type",
        "universe_snapshot_members",
        ["asset_type"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_universe_snapshot_members_asset_type", table_name="universe_snapshot_members")
    op.drop_table("universe_snapshot_members")
    op.drop_index("ix_universe_snapshots_created_at", table_name="universe_snapshots")
    op.drop_index("ix_universe_snapshots_effective_date", table_name="universe_snapshots")
    op.drop_table("universe_snapshots")
    op.drop_index("ix_data_quality_incidents_created_at", table_name="data_quality_incidents")
    op.drop_index(
        "ix_data_quality_incidents_resolution_status",
        table_name="data_quality_incidents",
    )
    op.drop_index("ix_data_quality_incidents_domain", table_name="data_quality_incidents")
    op.drop_index("ix_data_quality_incidents_trade_date", table_name="data_quality_incidents")
    op.drop_index("ix_data_quality_incidents_symbol", table_name="data_quality_incidents")
    op.drop_table("data_quality_incidents")
    op.drop_index(
        "ix_canonical_daily_bars_validation_tier",
        table_name="canonical_daily_bars",
    )
    op.drop_index("ix_canonical_daily_bars_trade_date", table_name="canonical_daily_bars")
    op.drop_table("canonical_daily_bars")
    op.drop_index(
        "ix_corporate_action_observations_action_type",
        table_name="corporate_action_observations",
    )
    op.drop_index(
        "ix_corporate_action_observations_ex_date",
        table_name="corporate_action_observations",
    )
    op.drop_index(
        "ix_corporate_action_observations_symbol",
        table_name="corporate_action_observations",
    )
    op.drop_index(
        "ix_corporate_action_observations_provider",
        table_name="corporate_action_observations",
    )
    op.drop_table("corporate_action_observations")
    op.drop_index("ix_daily_bar_observations_trade_date", table_name="daily_bar_observations")
    op.drop_index("ix_daily_bar_observations_symbol", table_name="daily_bar_observations")
    op.drop_table("daily_bar_observations")
    op.drop_index("ix_provider_payloads_requested_at", table_name="provider_payloads")
    op.drop_index("ix_provider_payloads_symbol", table_name="provider_payloads")
    op.drop_index("ix_provider_payloads_domain", table_name="provider_payloads")
    op.drop_index("ix_provider_payloads_provider", table_name="provider_payloads")
    op.drop_table("provider_payloads")
    op.drop_index("ix_backfill_runs_created_at", table_name="backfill_runs")
    op.drop_index("ix_backfill_runs_as_of_date", table_name="backfill_runs")
    op.drop_index("ix_backfill_runs_status", table_name="backfill_runs")
    op.drop_table("backfill_runs")
