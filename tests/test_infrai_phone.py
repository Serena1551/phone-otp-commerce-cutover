import httpx

from infrai_phone import InfraiPhoneClient


def test_send_code_retries_429_after_reading_envelope() -> None:
    attempts = 0
    delays: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        assert request.method == "POST"
        assert request.headers["Idempotency-Key"] == "login-attempt-42"
        if attempts == 1:
            return httpx.Response(
                429,
                headers={"Retry-After": "0.25"},
                json={"ok": False, "data": None, "error": {"code": "RATE_LIMITED"}, "metadata": {}},
            )
        return httpx.Response(
            200,
            json={"ok": True, "data": {"sent": True}, "error": None, "metadata": {}},
        )

    client = InfraiPhoneClient(
        "test-key",
        transport=httpx.MockTransport(handler),
        sleep=delays.append,
    )
    try:
        assert client.send_code("+14155550123", "login-attempt-42") == {"sent": True}
    finally:
        client.close()
    assert attempts == 2
    assert delays == [0.25]
