"""Create BRC admission gate Phase 1 facts

Revision ID: 018
Revises: 017
Create Date: 2026-05-27
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "018"
down_revision: Union[str, None] = "017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _jsonb_type() -> sa.types.TypeEngine:
    return postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite")


def _has_table(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def _has_index(table_name: str, index_name: str) -> bool:
    return any(
        index["name"] == index_name
        for index in sa.inspect(op.get_bind()).get_indexes(table_name)
    )


def _create_index_if_missing(
    index_name: str,
    table_name: str,
    columns: list[str],
    *,
    unique: bool = False,
) -> None:
    if _has_table(table_name) and not _has_index(table_name, index_name):
        op.create_index(index_name, table_name, columns, unique=unique)


def _drop_index_if_exists(index_name: str, table_name: str) -> None:
    if _has_table(table_name) and _has_index(table_name, index_name):
        op.drop_index(index_name, table_name=table_name)


def upgrade() -> None:
    if not _has_table("brc_strategy_families"):
        op.create_table(
            "brc_strategy_families",
            sa.Column("strategy_family_id", sa.String(length=128), nullable=False),
            sa.Column("family_key", sa.String(length=128), nullable=False),
            sa.Column("name", sa.String(length=256), nullable=False),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("owner", sa.String(length=128), nullable=False),
            sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
            sa.Column("updated_at_ms", sa.BIGINT(), nullable=False),
            sa.CheckConstraint(
                "status IN ('active', 'intake', 'parked', 'rejected')",
                name="ck_brc_strategy_families_status",
            ),
            sa.PrimaryKeyConstraint("strategy_family_id"),
            sa.UniqueConstraint("family_key"),
        )
    _create_index_if_missing(
        "idx_brc_strategy_families_status_time",
        "brc_strategy_families",
        ["status", "updated_at_ms"],
    )

    if not _has_table("brc_strategy_family_versions"):
        op.create_table(
            "brc_strategy_family_versions",
            sa.Column("strategy_family_version_id", sa.String(length=128), nullable=False),
            sa.Column("strategy_family_id", sa.String(length=128), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("hypothesis", sa.Text(), nullable=False),
            sa.Column("market_structure", sa.Text(), nullable=False),
            sa.Column("entry_logic_family", sa.Text(), nullable=False),
            sa.Column("exit_logic_family", sa.Text(), nullable=False),
            sa.Column("risk_model", sa.Text(), nullable=False),
            sa.Column("supported_symbols", _jsonb_type(), nullable=False),
            sa.Column("supported_timeframes", _jsonb_type(), nullable=False),
            sa.Column("required_data", _jsonb_type(), nullable=False),
            sa.Column("required_execution_capabilities", _jsonb_type(), nullable=False),
            sa.Column("known_failure_modes", _jsonb_type(), nullable=False),
            sa.Column("regime_contract_json", _jsonb_type(), nullable=False),
            sa.Column("safeguards_json", _jsonb_type(), nullable=False),
            sa.Column("degradation_policy_json", _jsonb_type(), nullable=False),
            sa.Column("playbook_id", sa.String(length=128), nullable=True),
            sa.Column("playbook_catalog_snapshot_json", _jsonb_type(), nullable=False),
            sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
            sa.Column("created_by", sa.String(length=128), nullable=False),
            sa.Column("is_current", sa.Boolean(), nullable=False),
            sa.CheckConstraint("version >= 1", name="ck_brc_strategy_family_versions_version"),
            sa.PrimaryKeyConstraint("strategy_family_version_id"),
        )
    _create_index_if_missing(
        "uq_brc_strategy_family_versions_family_version",
        "brc_strategy_family_versions",
        ["strategy_family_id", "version"],
        unique=True,
    )
    _create_index_if_missing(
        "idx_brc_strategy_family_versions_family",
        "brc_strategy_family_versions",
        ["strategy_family_id"],
    )

    if not _has_table("brc_admission_rule_configs"):
        op.create_table(
            "brc_admission_rule_configs",
            sa.Column("admission_rule_config_id", sa.String(length=128), nullable=False),
            sa.Column("config_key", sa.String(length=128), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("rule_details_json", _jsonb_type(), nullable=False),
            sa.Column("system_boundaries_json", _jsonb_type(), nullable=False),
            sa.Column("relaxable_safeguards_json", _jsonb_type(), nullable=False),
            sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
            sa.Column("created_by", sa.String(length=128), nullable=False),
            sa.CheckConstraint("version >= 1", name="ck_brc_admission_rule_configs_version"),
            sa.CheckConstraint(
                "status IN ('active', 'superseded', 'disabled')",
                name="ck_brc_admission_rule_configs_status",
            ),
            sa.PrimaryKeyConstraint("admission_rule_config_id"),
        )
    _create_index_if_missing(
        "uq_brc_admission_rule_configs_key_version",
        "brc_admission_rule_configs",
        ["config_key", "version"],
        unique=True,
    )
    _create_index_if_missing(
        "idx_brc_admission_rule_configs_status_time",
        "brc_admission_rule_configs",
        ["status", "created_at_ms"],
    )

    if not _has_table("brc_admission_evidence_packets"):
        op.create_table(
            "brc_admission_evidence_packets",
            sa.Column("evidence_packet_id", sa.String(length=128), nullable=False),
            sa.Column("strategy_family_version_id", sa.String(length=128), nullable=False),
            sa.Column("payload_json", _jsonb_type(), nullable=False),
            sa.Column("mandatory_complete", sa.Boolean(), nullable=False),
            sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
            sa.Column("created_by", sa.String(length=128), nullable=False),
            sa.PrimaryKeyConstraint("evidence_packet_id"),
        )
    _create_index_if_missing(
        "idx_brc_admission_evidence_packets_version",
        "brc_admission_evidence_packets",
        ["strategy_family_version_id"],
    )
    _create_index_if_missing(
        "idx_brc_admission_evidence_packets_time",
        "brc_admission_evidence_packets",
        ["created_at_ms"],
    )

    if not _has_table("brc_owner_market_regime_inputs"):
        op.create_table(
            "brc_owner_market_regime_inputs",
            sa.Column("owner_market_regime_input_id", sa.String(length=128), nullable=False),
            sa.Column("current_regime", sa.String(length=128), nullable=False),
            sa.Column("confidence", sa.String(length=64), nullable=False),
            sa.Column("rationale", sa.Text(), nullable=False),
            sa.Column("market_facts_snapshot_json", _jsonb_type(), nullable=False),
            sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
            sa.Column("created_by", sa.String(length=128), nullable=False),
            sa.PrimaryKeyConstraint("owner_market_regime_input_id"),
        )
    _create_index_if_missing(
        "idx_brc_owner_market_regime_inputs_time",
        "brc_owner_market_regime_inputs",
        ["created_at_ms"],
    )

    if not _has_table("brc_admission_requests"):
        op.create_table(
            "brc_admission_requests",
            sa.Column("admission_request_id", sa.String(length=128), nullable=False),
            sa.Column("strategy_family_version_id", sa.String(length=128), nullable=False),
            sa.Column("evidence_packet_id", sa.String(length=128), nullable=False),
            sa.Column("owner_market_regime_input_id", sa.String(length=128), nullable=False),
            sa.Column("trial_env", sa.String(length=16), nullable=False),
            sa.Column("trial_stage", sa.String(length=64), nullable=False),
            sa.Column("requested_execution_mode", sa.String(length=64), nullable=True),
            sa.Column("requested_risk_profile", sa.String(length=64), nullable=False),
            sa.Column("admission_rule_config_id", sa.String(length=128), nullable=True),
            sa.Column("account_facts_snapshot_ref", sa.String(length=256), nullable=True),
            sa.Column("account_facts_snapshot_json", _jsonb_type(), nullable=False),
            sa.Column("playbook_id", sa.String(length=128), nullable=True),
            sa.Column("playbook_catalog_snapshot_json", _jsonb_type(), nullable=False),
            sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
            sa.Column("requested_by", sa.String(length=128), nullable=False),
            sa.CheckConstraint(
                "trial_env IN ('testnet', 'live')",
                name="ck_brc_admission_requests_trial_env",
            ),
            sa.CheckConstraint(
                "trial_stage IN ('development_validation', 'funded_validation')",
                name="ck_brc_admission_requests_trial_stage",
            ),
            sa.CheckConstraint(
                "requested_execution_mode IS NULL OR requested_execution_mode IN "
                "('auto_within_budget', 'owner_confirm_each_entry', 'observe_only', 'no_entry')",
                name="ck_brc_admission_requests_execution_mode",
            ),
            sa.PrimaryKeyConstraint("admission_request_id"),
        )
    _create_index_if_missing(
        "idx_brc_admission_requests_version_time",
        "brc_admission_requests",
        ["strategy_family_version_id", "created_at_ms"],
    )
    _create_index_if_missing(
        "idx_brc_admission_requests_env_stage",
        "brc_admission_requests",
        ["trial_env", "trial_stage"],
    )

    if not _has_table("brc_trial_constraint_snapshots"):
        op.create_table(
            "brc_trial_constraint_snapshots",
            sa.Column("trial_constraint_snapshot_id", sa.String(length=128), nullable=False),
            sa.Column("admission_request_id", sa.String(length=128), nullable=False),
            sa.Column("status", sa.String(length=64), nullable=False),
            sa.Column("risk_profile", sa.String(length=64), nullable=False),
            sa.Column("risk_policy_version", sa.String(length=128), nullable=True),
            sa.Column("constraints_json", _jsonb_type(), nullable=False),
            sa.Column("risk_policy_snapshot_json", _jsonb_type(), nullable=False),
            sa.Column("adapter_result_json", _jsonb_type(), nullable=False),
            sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
            sa.Column("expires_at_ms", sa.BIGINT(), nullable=True),
            sa.CheckConstraint(
                "status IN ('pending_risk_capital_resolution', 'installable', "
                "'installed', 'expired', 'invalidated')",
                name="ck_brc_trial_constraint_snapshots_status",
            ),
            sa.PrimaryKeyConstraint("trial_constraint_snapshot_id"),
        )
    _create_index_if_missing(
        "idx_brc_trial_constraint_snapshots_request_time",
        "brc_trial_constraint_snapshots",
        ["admission_request_id", "created_at_ms"],
    )
    _create_index_if_missing(
        "idx_brc_trial_constraint_snapshots_status_time",
        "brc_trial_constraint_snapshots",
        ["status", "created_at_ms"],
    )

    if not _has_table("brc_admission_decisions"):
        op.create_table(
            "brc_admission_decisions",
            sa.Column("admission_decision_id", sa.String(length=128), nullable=False),
            sa.Column("admission_request_id", sa.String(length=128), nullable=False),
            sa.Column("decision", sa.String(length=64), nullable=False),
            sa.Column("trial_env", sa.String(length=16), nullable=False),
            sa.Column("trial_stage", sa.String(length=64), nullable=False),
            sa.Column("strategy_family_version_id", sa.String(length=128), nullable=False),
            sa.Column("playbook_id", sa.String(length=128), nullable=True),
            sa.Column("playbook_catalog_snapshot_json", _jsonb_type(), nullable=False),
            sa.Column("owner_market_regime_input_id", sa.String(length=128), nullable=False),
            sa.Column("evidence_packet_id", sa.String(length=128), nullable=False),
            sa.Column("admission_rule_config_id", sa.String(length=128), nullable=False),
            sa.Column("trial_constraint_snapshot_id", sa.String(length=128), nullable=False),
            sa.Column("risk_profile", sa.String(length=64), nullable=False),
            sa.Column("execution_mode", sa.String(length=64), nullable=False),
            sa.Column("degradation_applied", sa.Boolean(), nullable=False),
            sa.Column("risk_intent_json", _jsonb_type(), nullable=False),
            sa.Column("degradation_intent_json", _jsonb_type(), nullable=False),
            sa.Column("blockers_json", _jsonb_type(), nullable=False),
            sa.Column("warnings_json", _jsonb_type(), nullable=False),
            sa.Column("risk_disclosure_json", _jsonb_type(), nullable=False),
            sa.Column("known_gaps_json", _jsonb_type(), nullable=False),
            sa.Column("constraints_snapshot_json", _jsonb_type(), nullable=False),
            sa.Column("owner_risk_acceptance_id", sa.String(length=128), nullable=True),
            sa.Column("expires_at_ms", sa.BIGINT(), nullable=True),
            sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
            sa.CheckConstraint(
                "decision IN ('admit', 'admit_with_constraints', 'reject', 'park')",
                name="ck_brc_admission_decisions_decision",
            ),
            sa.CheckConstraint(
                "trial_env IN ('testnet', 'live')",
                name="ck_brc_admission_decisions_trial_env",
            ),
            sa.CheckConstraint(
                "trial_stage IN ('development_validation', 'funded_validation')",
                name="ck_brc_admission_decisions_trial_stage",
            ),
            sa.CheckConstraint(
                "execution_mode IN ('auto_within_budget', 'owner_confirm_each_entry', "
                "'observe_only', 'no_entry')",
                name="ck_brc_admission_decisions_execution_mode",
            ),
            sa.PrimaryKeyConstraint("admission_decision_id"),
        )
    _create_index_if_missing(
        "idx_brc_admission_decisions_request_time",
        "brc_admission_decisions",
        ["admission_request_id", "created_at_ms"],
    )
    _create_index_if_missing(
        "idx_brc_admission_decisions_decision_time",
        "brc_admission_decisions",
        ["decision", "created_at_ms"],
    )

    if not _has_table("brc_owner_risk_acceptances"):
        op.create_table(
            "brc_owner_risk_acceptances",
            sa.Column("owner_risk_acceptance_id", sa.String(length=128), nullable=False),
            sa.Column("admission_request_id", sa.String(length=128), nullable=False),
            sa.Column("admission_decision_id", sa.String(length=128), nullable=True),
            sa.Column("strategy_family_version_id", sa.String(length=128), nullable=False),
            sa.Column("trial_env", sa.String(length=16), nullable=False),
            sa.Column("trial_stage", sa.String(length=64), nullable=False),
            sa.Column("account_facts_snapshot_ref", sa.String(length=256), nullable=True),
            sa.Column("risk_profile", sa.String(length=64), nullable=False),
            sa.Column("risk_policy_snapshot_json", _jsonb_type(), nullable=False),
            sa.Column("constraint_snapshot_id", sa.String(length=128), nullable=False),
            sa.Column("risk_disclosure_snapshot_json", _jsonb_type(), nullable=False),
            sa.Column("known_gaps_snapshot_json", _jsonb_type(), nullable=False),
            sa.Column("owner_rationale", sa.Text(), nullable=False),
            sa.Column("confirmation_phrase", sa.String(length=128), nullable=False),
            sa.Column("confirmation_marker", sa.String(length=128), nullable=False),
            sa.Column("confirmed_at_ms", sa.BIGINT(), nullable=False),
            sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
            sa.Column("created_by", sa.String(length=128), nullable=False),
            sa.CheckConstraint(
                "trial_env IN ('testnet', 'live')",
                name="ck_brc_owner_risk_acceptances_trial_env",
            ),
            sa.CheckConstraint(
                "trial_stage IN ('development_validation', 'funded_validation')",
                name="ck_brc_owner_risk_acceptances_trial_stage",
            ),
            sa.PrimaryKeyConstraint("owner_risk_acceptance_id"),
        )
    _create_index_if_missing(
        "idx_brc_owner_risk_acceptances_request_time",
        "brc_owner_risk_acceptances",
        ["admission_request_id", "created_at_ms"],
    )
    _create_index_if_missing(
        "idx_brc_owner_risk_acceptances_constraint",
        "brc_owner_risk_acceptances",
        ["constraint_snapshot_id"],
    )

    if not _has_table("brc_admission_audit_log"):
        op.create_table(
            "brc_admission_audit_log",
            sa.Column("audit_id", sa.String(length=128), nullable=False),
            sa.Column("event_type", sa.String(length=128), nullable=False),
            sa.Column("ref_type", sa.String(length=128), nullable=False),
            sa.Column("ref_id", sa.String(length=128), nullable=False),
            sa.Column("admission_request_id", sa.String(length=128), nullable=True),
            sa.Column("admission_decision_id", sa.String(length=128), nullable=True),
            sa.Column("actor", sa.String(length=128), nullable=False),
            sa.Column("message", sa.Text(), nullable=False),
            sa.Column("metadata_json", _jsonb_type(), nullable=False),
            sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
            sa.PrimaryKeyConstraint("audit_id"),
        )
    _create_index_if_missing(
        "idx_brc_admission_audit_log_ref",
        "brc_admission_audit_log",
        ["ref_type", "ref_id"],
    )
    _create_index_if_missing(
        "idx_brc_admission_audit_log_request_time",
        "brc_admission_audit_log",
        ["admission_request_id", "created_at_ms"],
    )
    _create_index_if_missing(
        "idx_brc_admission_audit_log_time",
        "brc_admission_audit_log",
        ["created_at_ms"],
    )


def downgrade() -> None:
    for index_name, table_name in [
        ("idx_brc_admission_audit_log_time", "brc_admission_audit_log"),
        ("idx_brc_admission_audit_log_request_time", "brc_admission_audit_log"),
        ("idx_brc_admission_audit_log_ref", "brc_admission_audit_log"),
        ("idx_brc_owner_risk_acceptances_constraint", "brc_owner_risk_acceptances"),
        ("idx_brc_owner_risk_acceptances_request_time", "brc_owner_risk_acceptances"),
        ("idx_brc_admission_decisions_decision_time", "brc_admission_decisions"),
        ("idx_brc_admission_decisions_request_time", "brc_admission_decisions"),
        ("idx_brc_trial_constraint_snapshots_status_time", "brc_trial_constraint_snapshots"),
        ("idx_brc_trial_constraint_snapshots_request_time", "brc_trial_constraint_snapshots"),
        ("idx_brc_admission_requests_env_stage", "brc_admission_requests"),
        ("idx_brc_admission_requests_version_time", "brc_admission_requests"),
        ("idx_brc_owner_market_regime_inputs_time", "brc_owner_market_regime_inputs"),
        ("idx_brc_admission_evidence_packets_time", "brc_admission_evidence_packets"),
        ("idx_brc_admission_evidence_packets_version", "brc_admission_evidence_packets"),
        ("idx_brc_admission_rule_configs_status_time", "brc_admission_rule_configs"),
        ("uq_brc_admission_rule_configs_key_version", "brc_admission_rule_configs"),
        ("idx_brc_strategy_family_versions_family", "brc_strategy_family_versions"),
        ("uq_brc_strategy_family_versions_family_version", "brc_strategy_family_versions"),
        ("idx_brc_strategy_families_status_time", "brc_strategy_families"),
    ]:
        _drop_index_if_exists(index_name, table_name)

    for table_name in [
        "brc_admission_audit_log",
        "brc_owner_risk_acceptances",
        "brc_admission_decisions",
        "brc_trial_constraint_snapshots",
        "brc_admission_requests",
        "brc_owner_market_regime_inputs",
        "brc_admission_evidence_packets",
        "brc_admission_rule_configs",
        "brc_strategy_family_versions",
        "brc_strategy_families",
    ]:
        if _has_table(table_name):
            op.drop_table(table_name)
