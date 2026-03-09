"""Add Phase 3 fundamentals, features, and dataset snapshot tables."""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260309_000003"
down_revision = "20260309_000002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fundamental_observations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("metric_name", sa.String(length=64), nullable=False),
        sa.Column("source_concept", sa.String(length=128), nullable=False),
        sa.Column("fiscal_period_end", sa.Date(), nullable=False),
        sa.Column("fiscal_period_type", sa.String(length=16), nullable=False),
        sa.Column("filed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("unit", sa.String(length=16), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("form_type", sa.String(length=16), nullable=True),
        sa.Column("accession", sa.String(length=32), nullable=True),
        sa.Column("payload_id", sa.Integer(), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["payload_id"], ["provider_payloads.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_fundamental_observations_provider",
        "fundamental_observations",
        ["provider"],
        unique=False,
    )
    op.create_index(
        "ix_fundamental_observations_symbol",
        "fundamental_observations",
        ["symbol"],
        unique=False,
    )
    op.create_index(
        "ix_fundamental_observations_metric_name",
        "fundamental_observations",
        ["metric_name"],
        unique=False,
    )
    op.create_index(
        "ix_fundamental_observations_fiscal_period_end",
        "fundamental_observations",
        ["fiscal_period_end"],
        unique=False,
    )
    op.create_index(
        "ix_fundamental_observations_filed_at",
        "fundamental_observations",
        ["filed_at"],
        unique=False,
    )
    op.create_index(
        "ix_fundamental_observations_available_at",
        "fundamental_observations",
        ["available_at"],
        unique=False,
    )

    op.create_table(
        "feature_set_versions",
        sa.Column("version", sa.String(length=64), nullable=False),
        sa.Column("definition_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("version"),
    )
    op.create_index(
        "ix_feature_set_versions_created_at",
        "feature_set_versions",
        ["created_at"],
        unique=False,
    )

    op.create_table(
        "feature_snapshot_rows",
        sa.Column("feature_set_version", sa.String(length=64), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("universe_snapshot_id", sa.Integer(), nullable=True),
        sa.Column("values_json", sa.Text(), nullable=False),
        sa.Column("fundamentals_available_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["feature_set_version"], ["feature_set_versions.version"]),
        sa.ForeignKeyConstraint(["universe_snapshot_id"], ["universe_snapshots.id"]),
        sa.PrimaryKeyConstraint("feature_set_version", "symbol", "trade_date"),
    )
    op.create_index(
        "ix_feature_snapshot_rows_symbol",
        "feature_snapshot_rows",
        ["symbol"],
        unique=False,
    )
    op.create_index(
        "ix_feature_snapshot_rows_trade_date",
        "feature_snapshot_rows",
        ["trade_date"],
        unique=False,
    )

    op.create_table(
        "label_versions",
        sa.Column("version", sa.String(length=64), nullable=False),
        sa.Column("definition_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("version"),
    )
    op.create_index("ix_label_versions_created_at", "label_versions", ["created_at"], unique=False)

    op.create_table(
        "label_snapshot_rows",
        sa.Column("label_version", sa.String(length=64), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("values_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["label_version"], ["label_versions.version"]),
        sa.PrimaryKeyConstraint("label_version", "symbol", "trade_date"),
    )
    op.create_index(
        "ix_label_snapshot_rows_symbol",
        "label_snapshot_rows",
        ["symbol"],
        unique=False,
    )
    op.create_index(
        "ix_label_snapshot_rows_trade_date",
        "label_snapshot_rows",
        ["trade_date"],
        unique=False,
    )

    op.create_table(
        "dataset_snapshots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("universe_snapshot_id", sa.Integer(), nullable=True),
        sa.Column("feature_set_version", sa.String(length=64), nullable=False),
        sa.Column("label_version", sa.String(length=64), nullable=False),
        sa.Column("canonicalization_version", sa.String(length=64), nullable=False),
        sa.Column("generation_code_version", sa.String(length=64), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("null_statistics_json", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.Column("artifact_path", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["feature_set_version"], ["feature_set_versions.version"]),
        sa.ForeignKeyConstraint(["label_version"], ["label_versions.version"]),
        sa.ForeignKeyConstraint(["universe_snapshot_id"], ["universe_snapshots.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_dataset_snapshots_as_of_date",
        "dataset_snapshots",
        ["as_of_date"],
        unique=False,
    )
    op.create_index(
        "ix_dataset_snapshots_created_at",
        "dataset_snapshots",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_dataset_snapshots_created_at", table_name="dataset_snapshots")
    op.drop_index("ix_dataset_snapshots_as_of_date", table_name="dataset_snapshots")
    op.drop_table("dataset_snapshots")
    op.drop_index("ix_label_snapshot_rows_trade_date", table_name="label_snapshot_rows")
    op.drop_index("ix_label_snapshot_rows_symbol", table_name="label_snapshot_rows")
    op.drop_table("label_snapshot_rows")
    op.drop_index("ix_label_versions_created_at", table_name="label_versions")
    op.drop_table("label_versions")
    op.drop_index("ix_feature_snapshot_rows_trade_date", table_name="feature_snapshot_rows")
    op.drop_index("ix_feature_snapshot_rows_symbol", table_name="feature_snapshot_rows")
    op.drop_table("feature_snapshot_rows")
    op.drop_index("ix_feature_set_versions_created_at", table_name="feature_set_versions")
    op.drop_table("feature_set_versions")
    op.drop_index(
        "ix_fundamental_observations_available_at",
        table_name="fundamental_observations",
    )
    op.drop_index(
        "ix_fundamental_observations_filed_at",
        table_name="fundamental_observations",
    )
    op.drop_index(
        "ix_fundamental_observations_fiscal_period_end",
        table_name="fundamental_observations",
    )
    op.drop_index(
        "ix_fundamental_observations_metric_name",
        table_name="fundamental_observations",
    )
    op.drop_index("ix_fundamental_observations_symbol", table_name="fundamental_observations")
    op.drop_index("ix_fundamental_observations_provider", table_name="fundamental_observations")
    op.drop_table("fundamental_observations")
