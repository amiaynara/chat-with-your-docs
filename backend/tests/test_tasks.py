from app.tasks import ping


def test_ping_task_executes_eagerly_and_returns_pong():
    result = ping.delay()

    assert result.get(timeout=1) == "pong"
