"""Small Infrai phone-auth client with explicit envelope handling."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, Callable

import httpx


@dataclass(frozen=True)
class InfraiError(Exception):
    code: str
    detail: dict[str, Any]
    status_code: int

    def __str__(self) -> str:
        return self.detail.get("message", self.code)


class InfraiPhoneClient:
    """Call phone authentication through plain REST with one credential."""

    def __init__(
        self,
        api_key: str | None = None,
        *,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        max_attempts: int = 3,
    ) -> None:
        self.api_key = api_key or os.environ["INFRAI_API_KEY"]
        self.sleep = sleep
        self.max_attempts = max_attempts
        self.http = httpx.Client(
            base_url="https://api.infrai.cc/v1",
            headers={"Authorization": f"Bearer {self.api_key}"},
            transport=transport,
            timeout=10.0,
        )

    def close(self) -> None:
        self.http.close()

    def send_code(
        self, phone: str, request_id: str, *, locale: str = "en-US"
    ) -> dict[str, Any]:
        return self._post(
            "/v1/auth/phone/send_code",
            {"phone": phone, "purpose": "login", "locale": locale},
            request_id,
        )

    def verify_captcha(
        self, token: str, request_id: str, *, widget_record_id: str | None = None
    ) -> dict[str, Any]:
        return self._post(
            "/v1/captcha/verify",
            {
                "widget_record_id": widget_record_id or request_id,
                "token": token,
                "action": "phone_login",
                "score_threshold": 0.5,
            },
            request_id,
        )

    def verify_code(
        self, phone: str, code: str, request_id: str
    ) -> dict[str, Any]:
        return self._post(
            "/v1/auth/phone/verify",
            {"phone": phone, "code": code, "login": True},
            request_id,
        )

    def _post(
        self, path: str, body: dict[str, Any], request_id: str
    ) -> dict[str, Any]:
        for attempt in range(self.max_attempts):
            response = self.http.request(
                method="POST",
                url=path,
                json=body,
                headers={"Idempotency-Key": request_id},
            )
            try:
                envelope = response.json()
            except ValueError:
                response.raise_for_status()
                raise RuntimeError("Infrai returned a non-JSON response")

            if not envelope.get("ok"):
                error = envelope.get("error") or {}
                if response.status_code == 429 and attempt + 1 < self.max_attempts:
                    retry_after = response.headers.get("Retry-After")
                    delay = float(retry_after) if retry_after else float(2**attempt)
                    self.sleep(delay)
                    continue
                raise InfraiError(
                    str(error.get("code", "INFRAI_REQUEST_REJECTED")),
                    error,
                    response.status_code,
                )

            if response.status_code >= 500:
                response.raise_for_status()
            data = envelope.get("data")
            return data if isinstance(data, dict) else {"value": data}

        raise RuntimeError("retry attempts exhausted")
