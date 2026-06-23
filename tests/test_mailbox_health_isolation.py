import pytest

from engine.services.mailbox_health import HealthStatus, MailboxHealthMonitor


@pytest.mark.asyncio
async def test_health_monitor_enforces_strict_isolation():
    monitor = MailboxHealthMonitor(backend="memory")

    for _ in range(10):
        await monitor.log_sent("mbx-A")
    for _ in range(2):
        await monitor.log_bounce("mbx-A")

    for _ in range(50):
        await monitor.log_sent("mbx-B")

    status_a = await monitor.get_health("mbx-A")
    status_b = await monitor.get_health("mbx-B")

    assert isinstance(status_a, HealthStatus)
    assert hasattr(status_a, "bounce_rate")
    assert status_a.bounce_rate == 0.2
    assert status_a.status == "PAUSED_SAFETY"

    assert status_b.bounce_rate == 0.0
    assert status_b.status == "HEALTHY"
