"""Add Phase 5 portfolio, risk, and simulation execution tables."""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260309_000005"
down_revision = "20260309_000004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "system_mode_state",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("current_mode", sa.String(length=32), nullable=False),
        sa.Column("requested_mode", sa.String(length=32), nullable=True),
        sa.Column("live_profile", sa.String(length=32), nullable=False),
        sa.Column("is_frozen", sa.Boolean(), nullable=False),
        sa.Column("active_freeze_event_id", sa.Integer(), nullable=True),
        sa.Column("freeze_reason", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_system_mode_state_current_mode",
        "system_mode_state",
        ["current_mode"],
        unique=False,
    )

    op.create_table(
        "freeze_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("freeze_type", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("details_json", sa.Text(), nullable=False),
        sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cleared_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_freeze_events_status", "freeze_events", ["status"], unique=False)
    op.create_index(
        "ix_freeze_events_freeze_type",
        "freeze_events",
        ["freeze_type"],
        unique=False,
    )
    op.create_index("ix_freeze_events_source", "freeze_events", ["source"], unique=False)
    op.create_index(
        "ix_freeze_events_triggered_at",
        "freeze_events",
        ["triggered_at"],
        unique=False,
    )

    op.create_table(
        "simulation_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("mode", sa.String(length=32), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("decision_date", sa.Date(), nullable=True),
        sa.Column("model_entry_id", sa.Integer(), nullable=True),
        sa.Column("dataset_snapshot_id", sa.Integer(), nullable=True),
        sa.Column("regime", sa.String(length=32), nullable=True),
        sa.Column("gross_exposure_target", sa.Float(), nullable=False),
        sa.Column("gross_exposure_actual", sa.Float(), nullable=False),
        sa.Column("start_nav", sa.Float(), nullable=False),
        sa.Column("end_nav", sa.Float(), nullable=False),
        sa.Column("cash_start", sa.Float(), nullable=False),
        sa.Column("cash_end", sa.Float(), nullable=False),
        sa.Column("artifact_path", sa.Text(), nullable=True),
        sa.Column("summary_json", sa.Text(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["dataset_snapshot_id"], ["dataset_snapshots.id"]),
        sa.ForeignKeyConstraint(["model_entry_id"], ["model_registry_entries.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_simulation_runs_status", "simulation_runs", ["status"], unique=False)
    op.create_index("ix_simulation_runs_mode", "simulation_runs", ["mode"], unique=False)
    op.create_index(
        "ix_simulation_runs_as_of_date",
        "simulation_runs",
        ["as_of_date"],
        unique=False,
    )
    op.create_index(
        "ix_simulation_runs_decision_date",
        "simulation_runs",
        ["decision_date"],
        unique=False,
    )
    op.create_index("ix_simulation_runs_regime", "simulation_runs", ["regime"], unique=False)
    op.create_index(
        "ix_simulation_runs_created_at",
        "simulation_runs",
        ["created_at"],
        unique=False,
    )

    op.create_table(
        "portfolio_snapshots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("simulation_run_id", sa.Integer(), nullable=False),
        sa.Column("snapshot_type", sa.String(length=20), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("nav", sa.Float(), nullable=False),
        sa.Column("cash_balance", sa.Float(), nullable=False),
        sa.Column("gross_exposure", sa.Float(), nullable=False),
        sa.Column("net_exposure", sa.Float(), nullable=False),
        sa.Column("holding_count", sa.Integer(), nullable=False),
        sa.Column("turnover_ratio", sa.Float(), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["simulation_run_id"], ["simulation_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_portfolio_snapshots_simulation_run_id",
        "portfolio_snapshots",
        ["simulation_run_id"],
        unique=False,
    )
    op.create_index(
        "ix_portfolio_snapshots_snapshot_type",
        "portfolio_snapshots",
        ["snapshot_type"],
        unique=False,
    )
    op.create_index(
        "ix_portfolio_snapshots_trade_date",
        "portfolio_snapshots",
        ["trade_date"],
        unique=False,
    )
    op.create_index(
        "ix_portfolio_snapshots_created_at",
        "portfolio_snapshots",
        ["created_at"],
        unique=False,
    )

    op.create_table(
        "portfolio_snapshot_positions",
        sa.Column("snapshot_id", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("target_weight", sa.Float(), nullable=False),
        sa.Column("actual_weight", sa.Float(), nullable=False),
        sa.Column("shares", sa.Float(), nullable=False),
        sa.Column("price", sa.Float(), nullable=False),
        sa.Column("market_value", sa.Float(), nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("sector", sa.String(length=64), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["snapshot_id"], ["portfolio_snapshots.id"]),
        sa.PrimaryKeyConstraint("snapshot_id", "symbol"),
    )
    op.create_index(
        "ix_portfolio_snapshot_positions_sector",
        "portfolio_snapshot_positions",
        ["sector"],
        unique=False,
    )

    op.create_table(
        "order_intents",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("simulation_run_id", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("side", sa.String(length=8), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("order_type", sa.String(length=32), nullable=False),
        sa.Column("time_in_force", sa.String(length=16), nullable=False),
        sa.Column("requested_shares", sa.Float(), nullable=False),
        sa.Column("requested_notional", sa.Float(), nullable=False),
        sa.Column("limit_price", sa.Float(), nullable=True),
        sa.Column("reference_price", sa.Float(), nullable=False),
        sa.Column("expected_slippage_bps", sa.Float(), nullable=False),
        sa.Column("target_weight", sa.Float(), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["simulation_run_id"], ["simulation_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_order_intents_simulation_run_id",
        "order_intents",
        ["simulation_run_id"],
        unique=False,
    )
    op.create_index("ix_order_intents_symbol", "order_intents", ["symbol"], unique=False)
    op.create_index("ix_order_intents_status", "order_intents", ["status"], unique=False)
    op.create_index("ix_order_intents_created_at", "order_intents", ["created_at"], unique=False)

    op.create_table(
        "execution_fills",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("simulation_run_id", sa.Integer(), nullable=False),
        sa.Column("order_intent_id", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("side", sa.String(length=8), nullable=False),
        sa.Column("fill_status", sa.String(length=20), nullable=False),
        sa.Column("filled_shares", sa.Float(), nullable=False),
        sa.Column("filled_notional", sa.Float(), nullable=False),
        sa.Column("fill_price", sa.Float(), nullable=False),
        sa.Column("commission", sa.Float(), nullable=False),
        sa.Column("slippage_bps", sa.Float(), nullable=False),
        sa.Column("expected_spread_bps", sa.Float(), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.Column("filled_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["order_intent_id"], ["order_intents.id"]),
        sa.ForeignKeyConstraint(["simulation_run_id"], ["simulation_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_execution_fills_simulation_run_id",
        "execution_fills",
        ["simulation_run_id"],
        unique=False,
    )
    op.create_index("ix_execution_fills_symbol", "execution_fills", ["symbol"], unique=False)
    op.create_index(
        "ix_execution_fills_fill_status",
        "execution_fills",
        ["fill_status"],
        unique=False,
    )
    op.create_index("ix_execution_fills_filled_at", "execution_fills", ["filled_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_execution_fills_filled_at", table_name="execution_fills")
    op.drop_index("ix_execution_fills_fill_status", table_name="execution_fills")
    op.drop_index("ix_execution_fills_symbol", table_name="execution_fills")
    op.drop_index("ix_execution_fills_simulation_run_id", table_name="execution_fills")
    op.drop_table("execution_fills")
    op.drop_index("ix_order_intents_created_at", table_name="order_intents")
    op.drop_index("ix_order_intents_status", table_name="order_intents")
    op.drop_index("ix_order_intents_symbol", table_name="order_intents")
    op.drop_index("ix_order_intents_simulation_run_id", table_name="order_intents")
    op.drop_table("order_intents")
    op.drop_index(
        "ix_portfolio_snapshot_positions_sector",
        table_name="portfolio_snapshot_positions",
    )
    op.drop_table("portfolio_snapshot_positions")
    op.drop_index("ix_portfolio_snapshots_created_at", table_name="portfolio_snapshots")
    op.drop_index("ix_portfolio_snapshots_trade_date", table_name="portfolio_snapshots")
    op.drop_index(
        "ix_portfolio_snapshots_snapshot_type",
        table_name="portfolio_snapshots",
    )
    op.drop_index(
        "ix_portfolio_snapshots_simulation_run_id",
        table_name="portfolio_snapshots",
    )
    op.drop_table("portfolio_snapshots")
    op.drop_index("ix_simulation_runs_created_at", table_name="simulation_runs")
    op.drop_index("ix_simulation_runs_regime", table_name="simulation_runs")
    op.drop_index("ix_simulation_runs_decision_date", table_name="simulation_runs")
    op.drop_index("ix_simulation_runs_as_of_date", table_name="simulation_runs")
    op.drop_index("ix_simulation_runs_mode", table_name="simulation_runs")
    op.drop_index("ix_simulation_runs_status", table_name="simulation_runs")
    op.drop_table("simulation_runs")
    op.drop_index("ix_freeze_events_triggered_at", table_name="freeze_events")
    op.drop_index("ix_freeze_events_source", table_name="freeze_events")
    op.drop_index("ix_freeze_events_freeze_type", table_name="freeze_events")
    op.drop_index("ix_freeze_events_status", table_name="freeze_events")
    op.drop_table("freeze_events")
    op.drop_index("ix_system_mode_state_current_mode", table_name="system_mode_state")
    op.drop_table("system_mode_state")
