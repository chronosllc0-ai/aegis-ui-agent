"""Runtime event store filter coverage for observability event log."""

from __future__ import annotations

from backend.runtime_telemetry import RuntimeEventStore


def test_runtime_event_store_filters_platform_integration_user_status() -> None:
    """Event list should support platform/integration/user/status filters."""
    store = RuntimeEventStore(ttl_seconds=3600, max_events=1000)
    store.append(
        category="pairing.requested",
        subsystem="pairing",
        level="info",
        message="Pairing requested",
        details={
            "platform": "telegram",
            "integration_id": "int-1",
            "external_user_id": "ext-1",
            "status": "pending",
        },
    )
    store.append(
        category="policy.updated",
        subsystem="policy",
        level="info",
        message="Policy updated",
        details={
            "platform": "slack",
            "integration_id": "int-2",
            "actor_user_id": "owner-1",
            "status": "updated",
        },
    )

    by_platform = store.list_events(platform="telegram", limit=50)["events"]
    assert len(by_platform) == 1
    assert by_platform[0]["category"] == "pairing.requested"

    by_integration = store.list_events(integration="int-2", limit=50)["events"]
    assert len(by_integration) == 1
    assert by_integration[0]["category"] == "policy.updated"

    by_user = store.list_events(user="owner-1", limit=50)["events"]
    assert len(by_user) == 1
    assert by_user[0]["category"] == "policy.updated"

    by_status = store.list_events(status="pending", limit=50)["events"]
    assert len(by_status) == 1
    assert by_status[0]["category"] == "pairing.requested"
