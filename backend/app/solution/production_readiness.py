"""Production readiness checks for the customer engagement entry points."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping
from urllib.parse import urlsplit


_TRUE_VALUES = {"1", "true", "yes", "on"}
_LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}


def _enabled(value: str | None) -> bool:
    return (value or "").strip().casefold() in _TRUE_VALUES


def _status(ok: bool, production_mode: bool) -> str:
    if ok:
        return "ok"
    return "error" if production_mode else "warning"


def _check(name: str, ok: bool, detail: str, production_mode: bool) -> dict[str, str]:
    return {
        "name": name,
        "status": _status(ok, production_mode),
        "detail": detail,
    }


def _database_ok(raw_path: str, project_root: Path) -> bool:
    if not raw_path.strip():
        return False
    try:
        path = Path(raw_path).expanduser().resolve()
    except (OSError, RuntimeError):
        return False
    if path == project_root or path.is_relative_to(project_root):
        return False
    if path.exists() and not path.is_file():
        return False
    parent = path.parent
    return parent.is_dir() and os.access(parent, os.W_OK | os.X_OK)


def _public_url_ok(raw_url: str) -> bool:
    try:
        parsed = urlsplit(raw_url.strip())
    except ValueError:
        return False
    hostname = (parsed.hostname or "").casefold()
    return parsed.scheme == "https" and bool(hostname) and hostname not in _LOOPBACK_HOSTS


def evaluate_production_readiness(
    environ: Mapping[str, str] | None = None,
    *,
    project_root: Path | None = None,
) -> dict[str, object]:
    """Return secret-free checks and a production-aware readiness decision."""
    values = os.environ if environ is None else environ
    root = (project_root or Path(__file__).resolve().parents[3]).resolve()
    production_mode = _enabled(values.get("DCFORGE_PRODUCTION_MODE"))
    checks: list[dict[str, str]] = []

    llm_ok = all(
        values.get(name, "").strip()
        for name in ("LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL")
    )
    checks.append(
        _check(
            "llm",
            llm_ok,
            "模型调用配置完整" if llm_ok else "模型调用配置不完整",
            production_mode,
        )
    )

    database_ok = _database_ok(values.get("DCFORGE_DATABASE_PATH", ""), root)
    checks.append(
        _check(
            "workspace_database",
            database_ok,
            (
                "工作区数据库位于 Git 工作树外且父目录可写"
                if database_ok
                else "工作区数据库缺失、不可写或位于 Git 工作树内"
            ),
            production_mode,
        )
    )

    public_url_ok = _public_url_ok(values.get("CUSTOMER_PORTAL_BASE_URL", ""))
    checks.append(
        _check(
            "customer_portal_url",
            public_url_ok,
            (
                "客户入口使用公网 HTTPS 地址"
                if public_url_ok
                else "客户入口必须使用非本机的 HTTPS 地址"
            ),
            production_mode,
        )
    )

    internal_token_ok = len(
        values.get("CUSTOMER_ENGAGEMENT_INTERNAL_TOKEN", "").strip()
    ) >= 32
    checks.append(
        _check(
            "internal_access_token",
            internal_token_ok,
            (
                "内部访问令牌长度符合要求"
                if internal_token_ok
                else "内部访问令牌至少需要 32 个字符"
            ),
            production_mode,
        )
    )

    feishu_ok = all(
        values.get(name, "").strip() for name in ("FEISHU_APP_ID", "FEISHU_APP_SECRET")
    )
    checks.append(
        _check(
            "feishu",
            feishu_ok,
            "飞书应用配置完整" if feishu_ok else "飞书应用配置不完整",
            production_mode,
        )
    )

    internal_ids_ok = bool(values.get("FEISHU_INTERNAL_OPEN_IDS", "").strip())
    checks.append(
        _check(
            "feishu_internal_users",
            internal_ids_ok,
            (
                "已配置企业内部用户"
                if internal_ids_ok
                else "至少需要配置一个企业内部用户 open_id"
            ),
            production_mode,
        )
    )

    allowed_open_id = values.get("FEISHU_ALLOWED_OPEN_ID", "").strip()
    checks.append(
        {
            "name": "feishu_customer_scope",
            "status": "warning" if allowed_open_id else "ok",
            "detail": (
                "当前只允许一个 open_id 使用机器人"
                if allowed_open_id
                else "机器人未被单客户 open_id 限制"
            ),
        }
    )

    raw_workers = values.get("WEB_CONCURRENCY", "1").strip() or "1"
    try:
        worker_count = int(raw_workers)
    except ValueError:
        worker_count = 0
    worker_ok = worker_count >= 1
    checks.append(
        _check(
            "worker_model",
            worker_ok,
            (
                f"SQLite 工作区允许 {worker_count} 个 worker"
                if worker_ok
                else "WEB_CONCURRENCY 必须是正整数"
            ),
            production_mode,
        )
    )

    ready = not any(check["status"] == "error" for check in checks)
    return {
        "status": "ready" if ready else "not_ready",
        "service": "dcforge-solution",
        "production_mode": production_mode,
        "checks": checks,
    }
