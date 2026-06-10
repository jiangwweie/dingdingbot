"""Static script risk classification for BRC operator scripts.

The classifier reads script text and returns a conservative risk grade. It does
not import, execute, or shell out to any script.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class ScriptRiskCategory(str, Enum):
    DECLARED_READ_ONLY = "declared_read_only"
    EXCHANGE_READ = "exchange_read"
    EXCHANGE_WRITE = "exchange_write"
    DATABASE_WRITE = "database_write"
    REMOTE_DEPLOYMENT = "remote_deployment"
    RUNTIME_CONTROL = "runtime_control"
    LIVE_SCOPE = "live_scope"
    TESTNET_SCOPE = "testnet_scope"
    CREDENTIAL_SENSITIVE = "credential_sensitive"
    OWNER_AUTH_REQUIRED = "owner_auth_required"
    UNKNOWN = "unknown"


class ScriptRiskLevel(str, Enum):
    READ_ONLY = "read_only"
    REVIEW_REQUIRED = "review_required"
    MUTATION_RESTRICTED = "mutation_restricted"
    EXCHANGE_WRITE_RESTRICTED = "exchange_write_restricted"
    LIVE_ACTION_RESTRICTED = "live_action_restricted"
    UNKNOWN_REVIEW_REQUIRED = "unknown_review_required"


@dataclass(frozen=True)
class ScriptRiskSignal:
    category: ScriptRiskCategory
    code: str
    line_number: int
    evidence: str
    reason: str


@dataclass(frozen=True)
class ScriptRiskClassification:
    path: str
    level: ScriptRiskLevel
    categories: tuple[ScriptRiskCategory, ...]
    signals: tuple[ScriptRiskSignal, ...]
    default_allowed: bool
    owner_confirmation_required: bool
    live_action_possible: bool
    exchange_write_possible: bool
    database_write_possible: bool
    runtime_control_possible: bool
    containment_notes: tuple[str, ...]


@dataclass(frozen=True)
class _RiskPattern:
    category: ScriptRiskCategory
    code: str
    regex: re.Pattern[str]
    reason: str


_PATTERNS: tuple[_RiskPattern, ...] = (
    _RiskPattern(
        ScriptRiskCategory.DECLARED_READ_ONLY,
        "declared_read_only",
        re.compile(
            r"\b(read-only|research-only|dry-run|dry run|does not (?:modify|write|place|create execution|call exchange)|"
            r"never (?:places|cancels|replaces|flattens|prints))\b",
            re.IGNORECASE,
        ),
        "The script declares read-only or dry-run behavior.",
    ),
    _RiskPattern(
        ScriptRiskCategory.EXCHANGE_WRITE,
        "exchange_write_marker",
        re.compile(
            r"\b(create_order|place_order|submit_order|cancel_order|cancel_all_orders|close_position|"
            r"force_exchange_flat|execute-controlled-entry)\b|"
            r"\.delete\([^)]*/fapi/v1/order|\.post\([^)]*/fapi/v1/order|"
            r"\bExecutionOrchestrator\b|\bOrderLifecycleService\b",
            re.IGNORECASE,
        ),
        "The script can submit, close, cancel, or route orders.",
    ),
    _RiskPattern(
        ScriptRiskCategory.EXCHANGE_READ,
        "exchange_read_marker",
        re.compile(
            r"\bExchangeGateway\b|\bfetch_positions\b|\bfetch_open_orders\b|"
            r"\brun_exchange_credential_preflight\b|include_exchange=true|"
            r"/fapi/v[12]/(?:account|positionRisk|openOrders)",
            re.IGNORECASE,
        ),
        "The script can read exchange/account/order facts.",
    ),
    _RiskPattern(
        ScriptRiskCategory.DATABASE_WRITE,
        "database_write_marker",
        re.compile(
            r"\bINSERT\s+INTO\b|\bUPDATE\s+[A-Za-z0-9_\\.]+\s+SET\b|\bDELETE\s+FROM\b|"
            r"\bUPSERT\b|\bON CONFLICT\b|"
            r"\b(?:session|connection)\.commit\(|\breset_trade_count\b|"
            r"\bset_state\(|\bRuntimeProfileRepository\b|APPLY=true|"
            r"\balembic\s+upgrade\b",
            re.IGNORECASE,
        ),
        "The script can mutate database or persisted runtime/config state.",
    ),
    _RiskPattern(
        ScriptRiskCategory.REMOTE_DEPLOYMENT,
        "remote_deployment_marker",
        re.compile(
            r"\bscp\b|\bpg_dump\b|\btar\s+-xzf\b|\bln\s+-sfn\b|"
            r"\bsystemctl\s+(?:stop|start|restart|reload)\b",
            re.IGNORECASE,
        ),
        "The script can transfer release artifacts, change remote symlinks, backup PG, or control deployed services.",
    ),
    _RiskPattern(
        ScriptRiskCategory.RUNTIME_CONTROL,
        "runtime_control_marker",
        re.compile(
            r"/api/runtime/control|startup-trading-guard|global-kill-switch|"
            r"/api/brc/operations/(?:preflight|[^/]+/confirm)|"
            r"python -m src\.main|RUNTIME_PROFILE=",
            re.IGNORECASE,
        ),
        "The script touches runtime control, operation-layer, or runtime process state.",
    ),
    _RiskPattern(
        ScriptRiskCategory.LIVE_SCOPE,
        "live_scope_marker",
        re.compile(
            r"TRADING_ENV[\"'=:\s]+live|EXCHANGE_TESTNET[\"'=:\s]+false|"
            r"\btestnet=False\b|\blive_authorized\b|\blive_ready\b|"
            r"\blive acceptance\b|\bOwner-approved scope\b",
            re.IGNORECASE,
        ),
        "The script references live or live-authorization scope.",
    ),
    _RiskPattern(
        ScriptRiskCategory.TESTNET_SCOPE,
        "testnet_scope_marker",
        re.compile(r"EXCHANGE_TESTNET[\"'=:\s]+true|\btestnet\b|testnet\.binance", re.IGNORECASE),
        "The script references testnet scope.",
    ),
    _RiskPattern(
        ScriptRiskCategory.CREDENTIAL_SENSITIVE,
        "credential_sensitive_marker",
        re.compile(
            r"EXCHANGE_API_(?:KEY|SECRET)|api_secret|api_key|BRC_OPERATOR_SESSION_SECRET|"
            r"BRC_OPERATOR_TOTP_SECRET|OWNER_BOUNDED_SESSION_COOKIE|TREND_EXECUTE_SESSION_COOKIE|"
            r"\bsign\(",
            re.IGNORECASE,
        ),
        "The script touches credentials, signed sessions, or secret-derived values.",
    ),
    _RiskPattern(
        ScriptRiskCategory.OWNER_AUTH_REQUIRED,
        "owner_authorization_marker",
        re.compile(
            r"OWNER_APPROVED|Owner-approved|explicit Owner|confirmation_phrase|owner authorization|"
            r"owner-confirmed",
            re.IGNORECASE,
        ),
        "The script declares an Owner authorization or confirmation dependency.",
    ),
)

_SUPPORTED_SUFFIXES = {".py", ".sh"}


def classify_script_path(path: str | Path) -> ScriptRiskClassification:
    """Classify a script file without executing or importing it."""

    script_path = Path(path)
    text = script_path.read_text(encoding="utf-8", errors="replace")
    return classify_script_text(path=str(script_path), text=text)


def classify_script_text(*, path: str, text: str) -> ScriptRiskClassification:
    """Classify script source text using conservative static markers."""

    signals = _scan_signals(path=path, text=text)
    categories = tuple(sorted({signal.category for signal in signals}, key=lambda item: item.value))
    if not categories:
        signals = (
            ScriptRiskSignal(
                category=ScriptRiskCategory.UNKNOWN,
                code="no_static_risk_markers",
                line_number=0,
                evidence="",
                reason="No known safety or risk markers were found; fail closed for review.",
            ),
        )
        categories = (ScriptRiskCategory.UNKNOWN,)

    level = _risk_level(path=path, categories=categories)
    default_allowed = level is ScriptRiskLevel.READ_ONLY
    owner_confirmation_required = level in {
        ScriptRiskLevel.MUTATION_RESTRICTED,
        ScriptRiskLevel.EXCHANGE_WRITE_RESTRICTED,
        ScriptRiskLevel.LIVE_ACTION_RESTRICTED,
        ScriptRiskLevel.UNKNOWN_REVIEW_REQUIRED,
    } or ScriptRiskCategory.OWNER_AUTH_REQUIRED in categories

    return ScriptRiskClassification(
        path=path,
        level=level,
        categories=categories,
        signals=signals,
        default_allowed=default_allowed,
        owner_confirmation_required=owner_confirmation_required,
        live_action_possible=ScriptRiskCategory.LIVE_SCOPE in categories
        and ScriptRiskCategory.EXCHANGE_WRITE in categories,
        exchange_write_possible=ScriptRiskCategory.EXCHANGE_WRITE in categories,
        database_write_possible=ScriptRiskCategory.DATABASE_WRITE in categories,
        runtime_control_possible=ScriptRiskCategory.RUNTIME_CONTROL in categories,
        containment_notes=_containment_notes(level=level, categories=categories),
    )


def _scan_signals(*, path: str, text: str) -> tuple[ScriptRiskSignal, ...]:
    signals: list[ScriptRiskSignal] = []
    suffix = Path(path).suffix
    if suffix and suffix not in _SUPPORTED_SUFFIXES:
        return (
            ScriptRiskSignal(
                category=ScriptRiskCategory.UNKNOWN,
                code="unsupported_script_suffix",
                line_number=0,
                evidence=suffix,
                reason="Only Python and shell scripts are classified by this scanner.",
            ),
        )

    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        for pattern in _PATTERNS:
            if pattern.regex.search(line):
                signals.append(
                    ScriptRiskSignal(
                        category=pattern.category,
                        code=pattern.code,
                        line_number=line_number,
                        evidence=line[:180],
                        reason=pattern.reason,
                    )
                )
    return tuple(signals)


def _risk_level(*, path: str, categories: tuple[ScriptRiskCategory, ...]) -> ScriptRiskLevel:
    if ScriptRiskCategory.UNKNOWN in categories:
        return ScriptRiskLevel.UNKNOWN_REVIEW_REQUIRED
    if ScriptRiskCategory.EXCHANGE_WRITE in categories and ScriptRiskCategory.LIVE_SCOPE in categories:
        return ScriptRiskLevel.LIVE_ACTION_RESTRICTED
    if ScriptRiskCategory.EXCHANGE_WRITE in categories:
        return ScriptRiskLevel.EXCHANGE_WRITE_RESTRICTED
    if (
        ScriptRiskCategory.RUNTIME_CONTROL in categories
        or ScriptRiskCategory.DATABASE_WRITE in categories
        or ScriptRiskCategory.REMOTE_DEPLOYMENT in categories
    ):
        return ScriptRiskLevel.MUTATION_RESTRICTED
    if (
        ScriptRiskCategory.EXCHANGE_READ in categories
        or ScriptRiskCategory.CREDENTIAL_SENSITIVE in categories
        or ScriptRiskCategory.LIVE_SCOPE in categories
    ):
        return ScriptRiskLevel.REVIEW_REQUIRED
    if ScriptRiskCategory.DECLARED_READ_ONLY in categories:
        return ScriptRiskLevel.READ_ONLY

    lowered_path = path.lower()
    if any(token in lowered_path for token in ("analyze_", "research_", "backtest", "qa_")):
        return ScriptRiskLevel.READ_ONLY
    return ScriptRiskLevel.UNKNOWN_REVIEW_REQUIRED


def _containment_notes(
    *, level: ScriptRiskLevel, categories: tuple[ScriptRiskCategory, ...]
) -> tuple[str, ...]:
    notes: list[str] = []
    if level is ScriptRiskLevel.READ_ONLY:
        notes.append("May be inspected or run only as a read-only/research script.")
    elif level is ScriptRiskLevel.REVIEW_REQUIRED:
        notes.append("Requires explicit review before running because it touches exchange reads, credentials, or live scope.")
    elif level is ScriptRiskLevel.MUTATION_RESTRICTED:
        notes.append("Do not run by default; requires bounded Owner/Codex approval for the exact mutation scope.")
    elif level is ScriptRiskLevel.EXCHANGE_WRITE_RESTRICTED:
        notes.append("Do not run by default; exchange-write paths require an explicit controlled testnet or Owner-approved scope.")
    elif level is ScriptRiskLevel.LIVE_ACTION_RESTRICTED:
        notes.append("Do not run without separate explicit Owner authorization for the exact live action.")
    else:
        notes.append("Unknown scripts fail closed until manually reviewed and classified.")

    if ScriptRiskCategory.OWNER_AUTH_REQUIRED in categories:
        notes.append("Declared Owner authorization markers must be verified; declarations alone do not authorize execution.")
    if ScriptRiskCategory.TESTNET_SCOPE in categories and ScriptRiskCategory.EXCHANGE_WRITE in categories:
        notes.append("Testnet write scope is still a controlled execution rehearsal and must not imply live permission.")
    if ScriptRiskCategory.LIVE_SCOPE in categories and ScriptRiskCategory.EXCHANGE_WRITE not in categories:
        notes.append("Live-scope read/preflight scripts still require credential-safe review before use.")
    if ScriptRiskCategory.REMOTE_DEPLOYMENT in categories:
        notes.append("Remote deployment, migration, backup, symlink, or service-control commands require an explicit bounded deployment approval.")
    return tuple(notes)
