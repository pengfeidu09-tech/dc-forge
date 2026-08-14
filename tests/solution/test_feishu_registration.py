"""CHAT-M3 Feishu QR application-registration tests."""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import parse_qs

import httpx
import pytest

from backend.app.solution.feishu_registration import (
    FeishuAppRegistration,
    FeishuRegistrationDenied,
    FeishuRegistrationError,
    FeishuRegistrationExpired,
    FeishuRegistrationResult,
    FeishuRegistrationTimeout,
    persist_feishu_credentials,
)


def _client(
    responses: list[httpx.Response],
) -> tuple[FeishuAppRegistration, list[httpx.Request]]:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return responses.pop(0)

    return (
        FeishuAppRegistration(
            http_client=httpx.Client(transport=httpx.MockTransport(handler))
        ),
        requests,
    )


def test_init_requires_client_secret_auth_support() -> None:
    registration, requests = _client(
        [httpx.Response(200, json={"supported_auth_methods": ["private_key"]})]
    )

    with pytest.raises(FeishuRegistrationError, match="client_secret"):
        registration.initialize()

    assert parse_qs(requests[0].content.decode()) == {"action": ["init"]}


def test_begin_requests_personal_agent_and_builds_cli_qr_url() -> None:
    registration, requests = _client(
        [
            httpx.Response(
                200,
                json={
                    "device_code": "device-001",
                    "verification_uri": "https://accounts.feishu.cn/device",
                    "verification_uri_complete": (
                        "https://accounts.feishu.cn/device?user_code=ABCD"
                    ),
                    "user_code": "ABCD",
                    "interval": 3,
                    "expire_in": 600,
                },
            )
        ]
    )

    begin = registration.begin()

    assert begin.device_code == "device-001"
    assert begin.user_code == "ABCD"
    assert begin.interval == 3
    assert "from=dcforge_onboard" in begin.qr_url
    assert "tp=ob_cli_app" in begin.qr_url
    assert parse_qs(requests[0].content.decode()) == {
        "action": ["begin"],
        "archetype": ["PersonalAgent"],
        "auth_method": ["client_secret"],
        "request_user_info": ["open_id"],
    }


def test_poll_handles_pending_and_slow_down_before_success() -> None:
    registration, requests = _client(
        [
            httpx.Response(400, json={"error": "authorization_pending"}),
            httpx.Response(400, json={"error": "slow_down"}),
            httpx.Response(
                200,
                json={
                    "client_id": "cli_created",
                    "client_secret": "created-secret-value",
                    "user_info": {
                        "open_id": "ou_owner",
                        "tenant_brand": "feishu",
                    },
                },
            ),
        ]
    )
    sleeps: list[float] = []
    now = [0.0]

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        now[0] += seconds

    result = registration.poll(
        device_code="device-001",
        interval=2,
        expire_in=60,
        sleep=sleep,
        monotonic=lambda: now[0],
    )

    assert result == FeishuRegistrationResult(
        app_id="cli_created",
        app_secret="created-secret-value",
        domain="feishu",
        open_id="ou_owner",
    )
    assert sleeps == [2, 7]
    assert [parse_qs(request.content.decode()) for request in requests] == [
        {
            "action": ["poll"],
            "device_code": ["device-001"],
            "tp": ["ob_cli_app"],
        },
        {
            "action": ["poll"],
            "device_code": ["device-001"],
            "tp": ["ob_cli_app"],
        },
        {
            "action": ["poll"],
            "device_code": ["device-001"],
            "tp": ["ob_cli_app"],
        },
    ]


@pytest.mark.parametrize(
    ("error", "exception"),
    [
        ("access_denied", FeishuRegistrationDenied),
        ("expired_token", FeishuRegistrationExpired),
    ],
)
def test_poll_maps_terminal_errors(error: str, exception: type[Exception]) -> None:
    registration, _ = _client([httpx.Response(400, json={"error": error})])

    with pytest.raises(exception):
        registration.poll(
            device_code="device-001",
            interval=1,
            expire_in=10,
            sleep=lambda _: None,
        )


def test_poll_times_out_after_transient_network_failures() -> None:
    now = [0.0]

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("temporary failure", request=request)

    registration = FeishuAppRegistration(
        http_client=httpx.Client(transport=httpx.MockTransport(handler))
    )

    def sleep(seconds: float) -> None:
        now[0] += seconds

    with pytest.raises(FeishuRegistrationTimeout):
        registration.poll(
            device_code="device-001",
            interval=1,
            expire_in=2,
            sleep=sleep,
            monotonic=lambda: now[0],
        )


def test_unknown_poll_error_does_not_expose_server_description() -> None:
    registration, _ = _client(
        [
            httpx.Response(
                400,
                json={
                    "error": "unexpected_state",
                    "error_description": "created-secret-value must stay hidden",
                },
            )
        ]
    )

    with pytest.raises(FeishuRegistrationError) as captured:
        registration.poll(
            device_code="device-001",
            interval=1,
            expire_in=10,
            sleep=lambda _: None,
        )

    assert "unexpected_state" in str(captured.value)
    assert "created-secret-value" not in str(captured.value)


def test_persist_credentials_preserves_env_and_uses_private_permissions(
    tmp_path: Path,
) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "LLM_MODEL=deepseek-chat\nFEISHU_APP_ID=old-id\nCUSTOM=value\n",
        encoding="utf-8",
    )
    result = FeishuRegistrationResult(
        app_id="cli_created",
        app_secret="created-secret-value",
        domain="feishu",
        open_id="ou_owner",
    )

    persist_feishu_credentials(result, env_path)

    content = env_path.read_text(encoding="utf-8")
    assert "LLM_MODEL=deepseek-chat" in content
    assert "CUSTOM=value" in content
    assert content.count("FEISHU_APP_ID=") == 1
    assert 'FEISHU_APP_ID="cli_created"' in content
    assert 'FEISHU_APP_SECRET="created-secret-value"' in content
    assert 'FEISHU_ALLOWED_OPEN_ID="ou_owner"' in content
    assert 'FEISHU_API_BASE_URL="https://open.feishu.cn"' in content
    assert os.stat(env_path).st_mode & 0o777 == 0o600
