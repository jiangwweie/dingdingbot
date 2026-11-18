"""Phone execution is a certified feature of the existing exchange writer authority."""

from src.trading_kernel.application.ports import RuntimeCapabilitySnapshot

OWNER_COOPERATION_CONTRACT = "owner-cooperation-v1"


def owner_cooperation_enabled(
    capability: RuntimeCapabilitySnapshot | None,
    *,
    runtime_commit: str | None = None,
    schema_revision: str | None = None,
) -> bool:
    return bool(
        capability is not None
        and capability.enabled
        and capability.certification.get("owner_cooperation")
        == OWNER_COOPERATION_CONTRACT
        and (runtime_commit is None or capability.certified_commit == runtime_commit)
        and (schema_revision is None or capability.schema_revision == schema_revision)
    )
