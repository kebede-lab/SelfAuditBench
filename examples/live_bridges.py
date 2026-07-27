"""Minimal bridge construction examples for immutable benchmark snapshots."""

from selfauditbench.actors.strategies import NoAuditStrategy
from selfauditbench.adapters.live import ASBLiveBridge, BrokerRuntime, ConVerseLiveBridge
from selfauditbench.core.models import ActionType, CapabilityGrant, PermissionState


def asb_bridge() -> ASBLiveBridge:
    permissions = PermissionState(
        grants={
            "tool:market_data_api": CapabilityGrant(
                capability="tool:market_data_api", operations=(ActionType.TOOL_CALL.value,)
            ),
            "memory:write": CapabilityGrant(
                capability="memory:write", operations=(ActionType.MEMORY_WRITE.value,)
            ),
        }
    )
    return ASBLiveBridge(BrokerRuntime("asb-live-example", permissions, NoAuditStrategy()))


def converse_bridge() -> ConVerseLiveBridge:
    permissions = PermissionState(
        grants={
            "environment:query": CapabilityGrant(
                capability="environment:query", operations=(ActionType.ENVIRONMENT_QUERY.value,)
            ),
            "disclosure:external_agent": CapabilityGrant(
                capability="disclosure:external_agent", operations=(ActionType.DISCLOSURE.value,)
            ),
            "commit:final": CapabilityGrant(
                capability="commit:final", operations=(ActionType.COMMIT.value,)
            ),
        }
    )
    return ConVerseLiveBridge(
        BrokerRuntime("converse-live-example", permissions, NoAuditStrategy())
    )

