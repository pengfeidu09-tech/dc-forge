"""Feishu personal-agent registration for DCForge's own bot transport."""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx


FeishuDomain = Literal["feishu", "lark"]

_ACCOUNTS_URLS: dict[FeishuDomain, str] = {
    "feishu": "https://accounts.feishu.cn",
    "lark": "https://accounts.larksuite.com",
}
_API_URLS: dict[FeishuDomain, str] = {
    "feishu": "https://open.feishu.cn",
    "lark": "https://open.larksuite.com",
}
_REGISTRATION_PATH = "/oauth/v1/app/registration"
_ENV_ASSIGNMENT = re.compile(
    r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*="
)


def _set_private_file_permissions(path: Path) -> None:
    """Restrict a credential file to the current user on the host platform."""
    if os.name != "nt":
        os.chmod(path, 0o600)
        return

    identity = subprocess.run(
        ["whoami"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if not identity:
        raise OSError("unable to determine the current Windows identity")
    subprocess.run(
        [
            "icacls.exe",
            str(path),
            "/inheritance:r",
            "/grant:r",
            f"{identity}:(F)",
        ],
        check=True,
        capture_output=True,
        text=True,
    )


class FeishuRegistrationError(RuntimeError):
    """A sanitized Feishu application-registration failure."""


class FeishuRegistrationDenied(FeishuRegistrationError):
    """The operator denied the QR authorization request."""


class FeishuRegistrationExpired(FeishuRegistrationError):
    """The Feishu device code expired before authorization completed."""


class FeishuRegistrationTimeout(FeishuRegistrationError):
    """The local registration wait reached its deadline."""


class _TransientRegistrationError(FeishuRegistrationError):
    pass


@dataclass(frozen=True)
class FeishuRegistrationBegin:
    device_code: str
    qr_url: str
    user_code: str
    interval: int
    expire_in: int


@dataclass(frozen=True)
class FeishuRegistrationResult:
    app_id: str
    app_secret: str
    domain: FeishuDomain
    open_id: str | None = None


class FeishuAppRegistration:
    """Small client for Feishu's device-code PersonalAgent registration flow."""

    def __init__(
        self,
        *,
        domain: FeishuDomain = "feishu",
        http_client: httpx.Client | None = None,
        timeout: float = 10.0,
    ) -> None:
        self._domain = domain
        self._http_client = http_client
        self._timeout = timeout

    def _post(self, domain: FeishuDomain, data: dict[str, str]) -> dict:
        url = f"{_ACCOUNTS_URLS[domain]}{_REGISTRATION_PATH}"
        try:
            if self._http_client is not None:
                response = self._http_client.post(url, data=data)
            else:
                with httpx.Client(timeout=self._timeout) as client:
                    response = client.post(url, data=data)
        except (httpx.TimeoutException, httpx.RequestError) as error:
            raise _TransientRegistrationError(
                "Feishu registration network request failed"
            ) from error

        try:
            payload = response.json()
        except ValueError as error:
            raise FeishuRegistrationError(
                "Feishu registration returned invalid JSON"
            ) from error
        if not isinstance(payload, dict):
            raise FeishuRegistrationError(
                "Feishu registration returned an invalid payload"
            )
        if response.status_code >= 500:
            raise _TransientRegistrationError(
                f"Feishu registration failed with HTTP {response.status_code}"
            )
        if response.status_code >= 400 and not isinstance(payload.get("error"), str):
            raise FeishuRegistrationError(
                f"Feishu registration failed with HTTP {response.status_code}"
            )
        return payload

    def initialize(self) -> None:
        try:
            payload = self._post(self._domain, {"action": "init"})
        except _TransientRegistrationError as error:
            raise FeishuRegistrationError(str(error)) from error
        supported = payload.get("supported_auth_methods")
        if not isinstance(supported, list) or "client_secret" not in supported:
            raise FeishuRegistrationError(
                "Feishu registration does not support client_secret auth"
            )

    def begin(self) -> FeishuRegistrationBegin:
        try:
            payload = self._post(
                self._domain,
                {
                    "action": "begin",
                    "archetype": "PersonalAgent",
                    "auth_method": "client_secret",
                    "request_user_info": "open_id",
                },
            )
        except _TransientRegistrationError as error:
            raise FeishuRegistrationError(str(error)) from error

        required = {
            name: payload.get(name)
            for name in (
                "device_code",
                "verification_uri_complete",
                "user_code",
            )
        }
        if not all(isinstance(value, str) and value.strip() for value in required.values()):
            raise FeishuRegistrationError(
                "Feishu registration begin response omitted required fields"
            )

        interval = payload.get("interval")
        expire_in = payload.get("expire_in")
        if not isinstance(interval, int) or interval <= 0:
            interval = 5
        if not isinstance(expire_in, int) or expire_in <= 0:
            expire_in = 600

        qr_url = _with_registration_markers(required["verification_uri_complete"])
        return FeishuRegistrationBegin(
            device_code=required["device_code"],
            qr_url=qr_url,
            user_code=required["user_code"],
            interval=interval,
            expire_in=expire_in,
        )

    def poll(
        self,
        *,
        device_code: str,
        interval: int,
        expire_in: int,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> FeishuRegistrationResult:
        current_interval = interval if interval > 0 else 5
        deadline = monotonic() + (expire_in if expire_in > 0 else 600)
        domain = self._domain
        switched_domain = False

        while monotonic() < deadline:
            try:
                payload = self._post(
                    domain,
                    {
                        "action": "poll",
                        "device_code": device_code,
                        "tp": "ob_cli_app",
                    },
                )
            except _TransientRegistrationError:
                sleep(current_interval)
                continue

            user_info = payload.get("user_info")
            if not isinstance(user_info, dict):
                user_info = {}
            tenant_brand = user_info.get("tenant_brand")
            if tenant_brand == "lark" and domain != "lark" and not switched_domain:
                domain = "lark"
                switched_domain = True
                continue

            app_id = payload.get("client_id")
            app_secret = payload.get("client_secret")
            if (
                isinstance(app_id, str)
                and app_id.strip()
                and isinstance(app_secret, str)
                and app_secret.strip()
            ):
                open_id = user_info.get("open_id")
                return FeishuRegistrationResult(
                    app_id=app_id.strip(),
                    app_secret=app_secret.strip(),
                    domain=domain,
                    open_id=(
                        open_id.strip()
                        if isinstance(open_id, str) and open_id.strip()
                        else None
                    ),
                )

            error = payload.get("error")
            if error == "authorization_pending" or error is None:
                pass
            elif error == "slow_down":
                current_interval += 5
            elif error == "access_denied":
                raise FeishuRegistrationDenied("Feishu QR authorization was denied")
            elif error == "expired_token":
                raise FeishuRegistrationExpired("Feishu QR authorization expired")
            elif isinstance(error, str):
                raise FeishuRegistrationError(
                    f"Feishu QR authorization failed: {error}"
                )
            else:
                raise FeishuRegistrationError(
                    "Feishu QR authorization returned an invalid payload"
                )
            sleep(current_interval)

        raise FeishuRegistrationTimeout("Feishu QR authorization timed out")


def _with_registration_markers(url: str) -> str:
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.netloc:
        raise FeishuRegistrationError("Feishu registration returned an invalid QR URL")
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["from"] = "dcforge_onboard"
    query["tp"] = "ob_cli_app"
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment)
    )


def _env_quote(value: str) -> str:
    escaped = (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\r", "\\r")
        .replace("\n", "\\n")
    )
    return f'"{escaped}"'


def persist_feishu_credentials(
    result: FeishuRegistrationResult,
    env_path: str | Path = ".env",
) -> Path:
    """Atomically update local Feishu credentials without returning the secret."""
    path = Path(env_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    original = path.read_text(encoding="utf-8") if path.exists() else ""
    values = {
        "FEISHU_APP_ID": result.app_id,
        "FEISHU_APP_SECRET": result.app_secret,
        "FEISHU_API_BASE_URL": _API_URLS[result.domain],
    }
    if result.open_id:
        values["FEISHU_ALLOWED_OPEN_ID"] = result.open_id

    output: list[str] = []
    written: set[str] = set()
    for line in original.splitlines():
        match = _ENV_ASSIGNMENT.match(line)
        key = match.group(1) if match else None
        if key not in values:
            output.append(line)
            continue
        if key not in written:
            output.append(f"{key}={_env_quote(values[key])}")
            written.add(key)

    if output and output[-1] != "":
        output.append("")
    for key, value in values.items():
        if key not in written:
            output.append(f"{key}={_env_quote(value)}")
    content = "\n".join(output).rstrip("\n") + "\n"

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=str(path.parent), text=True
    )
    try:
        if hasattr(os, "fchmod"):
            os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        if os.name == "nt":
            _set_private_file_permissions(Path(temporary_name))
        os.replace(temporary_name, path)
        if os.name != "nt":
            _set_private_file_permissions(path)
    except Exception:
        try:
            os.close(descriptor)
        except OSError:
            pass
        try:
            os.unlink(temporary_name)
        except OSError:
            pass
        raise
    return path
