"""Add Phase 6 broker, approvals, and mode transition tables."""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260309_000006"
down_revision = "20260309_000005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mode_transition_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("previous_mode", sa.String(length=32), nullable=False),
        sa.Column("new_mode", sa.String(length=32), nullable=False),
        sa.Column("live_profile", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_mode_transition_events_previous_mode",
        "mode_transition_events",
        ["previous_mode"],
        unique=False,
    )
    op.create_index(
        "ix_mode_transition_events_new_mode",
        "mode_transition_events",
        ["new_mode"],
        unique=False,
    )
    op.create_index(
        "ix_mode_transition_events_source",
        "mode_transition_events",
        ["source"],
        unique=False,
    )
    op.create_index(
        "ix_mode_transition_events_created_at",
        "mode_transition_events",
        ["created_at"],
        unique=False,
    )

    op.create_table(
        "broker_account_snapshots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("simulation_run_id", sa.Integer(), nullable=True),
        sa.Column("broker_name", sa.String(length=64), nullable=False),
        sa.Column("mode", sa.String(length=32), nullable=False),
        sa.Column("account_id", sa.String(length=32), nullable=False),
        sa.Column("net_liquidation", sa.Float(), nullable=False),
        sa.Column("cash_balance", sa.Float(), nullable=False),
        sa.Column("buying_power", sa.Float(), nullable=False),
        sa.Column("available_funds", sa.Float(), nullable=False),
        sa.Column("cushion", sa.Float(), nullable=True),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["simulation_run_id"], ["simulation_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_broker_account_snapshots_simulation_run_id",
        "broker_account_snapshots",
        ["simulation_run_id"],
        unique=False,
    )
    op.create_index(
        "ix_broker_account_snapshots_broker_name",
        "broker_account_snapshots",
        ["broker_name"],
        unique=False,
    )
    op.create_index(
        "ix_broker_account_snapshots_mode",
        "broker_account_snapshots",
        ["mode"],
        unique=False,
    )
    op.create_index(
        "ix_broker_account_snapshots_account_id",
        "broker_account_snapshots",
        ["account_id"],
        unique=False,
    )
    op.create_index(
        "ix_broker_account_snapshots_captured_at",
        "broker_account_snapshots",
        ["captured_at"],
        unique=False,
    )

    op.create_table(
        "broker_position_snapshots",
        sa.Column("snapshot_id", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("quantity", sa.Float(), nullable=False),
        sa.Column("market_price", sa.Float(), nullable=False),
        sa.Column("market_value", sa.Float(), nullable=False),
        sa.Column("average_cost", sa.Float(), nullable=True),
        sa.Column("unrealized_pnl", sa.Float(), nullable=True),
        sa.Column("realized_pnl", sa.Float(), nullable=True),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["snapshot_id"], ["broker_account_snapshots.id"]),
        sa.PrimaryKeyConstraint("snapshot_id", "symbol"),
    )

    op.create_table(
        "broker_orders",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("simulation_run_id", sa.Integer(), nullable=False),
        sa.Column("order_intent_id", sa.Integer(), nullable=True),
        sa.Column("broker_name", sa.String(length=64), nullable=False),
        sa.Column("mode", sa.String(length=32), nullable=False),
        sa.Column("account_id", sa.String(length=32), nullable=False),
        sa.Column("broker_order_id", sa.String(length=64), nullable=True),
        sa.Column("broker_status", sa.String(length=32), nullable=False),
        sa.Column("approval_status", sa.String(length=32), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("side", sa.String(length=8), nullable=False),
        sa.Column("order_type", sa.String(length=32), nullable=False),
        sa.Column("time_in_force", sa.String(length=16), nullable=False),
        sa.Column("requested_shares", sa.Float(), nullable=False),
        sa.Column("filled_shares", sa.Float(), nullable=False),
        sa.Column("limit_price", sa.Float(), nullable=True),
        sa.Column("average_fill_price", sa.Float(), nullable=True),
        sa.Column("preview_commission", sa.Float(), nullable=True),
        sa.Column("warnings_json", sa.Text(), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["order_intent_id"], ["order_intents.id"]),
        sa.ForeignKeyConstraint(["simulation_run_id"], ["simulation_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_broker_orders_simulation_run_id",
        "broker_orders",
        ["simulation_run_id"],
        unique=False,
    )
    op.create_index(
        "ix_broker_orders_order_intent_id",
        "broker_orders",
        ["order_intent_id"],
        unique=False,
    )
    op.create_index("ix_broker_orders_broker_name", "broker_orders", ["broker_name"], unique=False)
    op.create_index("ix_broker_orders_mode", "broker_orders", ["mode"], unique=False)
    op.create_index("ix_broker_orders_account_id", "broker_orders", ["account_id"], unique=False)
    op.create_index(
        "ix_broker_orders_broker_order_id",
        "broker_orders",
        ["broker_order_id"],
        unique=False,
    )
    op.create_index(
        "ix_broker_orders_broker_status",
        "broker_orders",
        ["broker_status"],
        unique=False,
    )
    op.create_index(
        "ix_broker_orders_approval_status",
        "broker_orders",
        ["approval_status"],
        unique=False,
    )
    op.create_index("ix_broker_orders_symbol", "broker_orders", ["symbol"], unique=False)
    op.create_index("ix_broker_orders_created_at", "broker_orders", ["created_at"], unique=False)

    op.create_table(
        "order_approvals",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("simulation_run_id", sa.Integer(), nullable=False),
        sa.Column("order_intent_id", sa.Integer(), nullable=False),
        sa.Column("broker_order_id", sa.Integer(), nullable=True),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("mode", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("requested_by", sa.String(length=64), nullable=True),
        sa.Column("decided_by", sa.String(length=64), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["broker_order_id"], ["broker_orders.id"]),
        sa.ForeignKeyConstraint(["order_intent_id"], ["order_intents.id"]),
        sa.ForeignKeyConstraint(["simulation_run_id"], ["simulation_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_order_approvals_simulation_run_id",
        "order_approvals",
        ["simulation_run_id"],
        unique=False,
    )
    op.create_index(
        "ix_order_approvals_order_intent_id",
        "order_approvals",
        ["order_intent_id"],
        unique=False,
    )
    op.create_index(
        "ix_order_approvals_broker_order_id",
        "order_approvals",
        ["broker_order_id"],
        unique=False,
    )
    op.create_index("ix_order_approvals_symbol", "order_approvals", ["symbol"], unique=False)
    op.create_index("ix_order_approvals_mode", "order_approvals", ["mode"], unique=False)
    op.create_index("ix_order_approvals_status", "order_approvals", ["status"], unique=False)
    op.create_index(
        "ix_order_approvals_created_at",
        "order_approvals",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_order_approvals_created_at", table_name="order_approvals")
    op.drop_index("ix_order_approvals_status", table_name="order_approvals")
    op.drop_index("ix_order_approvals_mode", table_name="order_approvals")
    op.drop_index("ix_order_approvals_symbol", table_name="order_approvals")
    op.drop_index("ix_order_approvals_broker_order_id", table_name="order_approvals")
    op.drop_index("ix_order_approvals_order_intent_id", table_name="order_approvals")
    op.drop_index("ix_order_approvals_simulation_run_id", table_name="order_approvals")
    op.drop_table("order_approvals")

    op.drop_index("ix_broker_orders_created_at", table_name="broker_orders")
    op.drop_index("ix_broker_orders_symbol", table_name="broker_orders")
    op.drop_index("ix_broker_orders_approval_status", table_name="broker_orders")
    op.drop_index("ix_broker_orders_broker_status", table_name="broker_orders")
    op.drop_index("ix_broker_orders_broker_order_id", table_name="broker_orders")
    op.drop_index("ix_broker_orders_account_id", table_name="broker_orders")
    op.drop_index("ix_broker_orders_mode", table_name="broker_orders")
    op.drop_index("ix_broker_orders_broker_name", table_name="broker_orders")
    op.drop_index("ix_broker_orders_order_intent_id", table_name="broker_orders")
    op.drop_index("ix_broker_orders_simulation_run_id", table_name="broker_orders")
    op.drop_table("broker_orders")

    op.drop_table("broker_position_snapshots")

    op.drop_index("ix_broker_account_snapshots_captured_at", table_name="broker_account_snapshots")
    op.drop_index("ix_broker_account_snapshots_account_id", table_name="broker_account_snapshots")
    op.drop_index("ix_broker_account_snapshots_mode", table_name="broker_account_snapshots")
    op.drop_index("ix_broker_account_snapshots_broker_name", table_name="broker_account_snapshots")
    op.drop_index(
        "ix_broker_account_snapshots_simulation_run_id",
        table_name="broker_account_snapshots",
    )
    op.drop_table("broker_account_snapshots")

    op.drop_index("ix_mode_transition_events_created_at", table_name="mode_transition_events")
    op.drop_index("ix_mode_transition_events_source", table_name="mode_transition_events")
    op.drop_index("ix_mode_transition_events_new_mode", table_name="mode_transition_events")
    op.drop_index(
        "ix_mode_transition_events_previous_mode",
        table_name="mode_transition_events",
    )
    op.drop_table("mode_transition_events")
