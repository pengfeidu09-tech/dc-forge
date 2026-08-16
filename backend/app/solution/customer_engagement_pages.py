"""Built frontend entries for the PORTAL-M3 APIs."""

from __future__ import annotations

from pathlib import Path


def _frontend_dist(frontend_dist: str | Path | None) -> Path:
    return (
        Path(frontend_dist).resolve()
        if frontend_dist is not None
        else Path(__file__).resolve().parents[3] / "frontend" / "dist"
    )


def _build_fallback(title: str, description: str) -> str:
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="description" content="{description}">
  <title>{title}</title>
  <style>
    :root{{font-family:Inter,"PingFang SC",sans-serif;color:#253142;background:#f3f5f7}}
    body{{display:grid;min-height:100vh;margin:0;place-items:center}}
    main{{width:min(520px,calc(100% - 40px));padding:28px;background:#fff;border:1px solid #dfe4ea;border-radius:8px}}
    h1{{margin:0 0 10px;font-size:21px}}p{{margin:0;color:#6f7c8e;line-height:1.7}}code{{color:#2f6feb}}
  </style>
</head>
<body>
  <main>
    <h1>{title}</h1>
    <p>前端资源尚未构建。请在 <code>frontend/</code> 执行 <code>npm run build</code> 后重新加载。</p>
  </main>
</body>
</html>"""


def presales_workbench_html(
    frontend_dist: str | Path | None = None,
) -> str:
    """Return the Ant Design Vue workbench build or an explicit build fallback."""
    entry = _frontend_dist(frontend_dist) / "presales" / "workbench" / "index.html"
    if entry.is_file():
        return entry.read_text(encoding="utf-8")
    return _build_fallback(
        "统一售前工作台",
        "客户需求工作台，实时读取当前需求并生成演示方案",
    )


def internal_workbench_html() -> str:
    """Compatibility alias for the original customer engagement entry."""
    return presales_workbench_html()


def customer_center_html(
    access_id: str,
    frontend_dist: str | Path | None = None,
) -> str:
    """Return the Ant Design Vue customer center build.

    The access ID stays in the request path and is read by the frontend. It is not
    interpolated into executable HTML.
    """
    if not access_id.strip():
        raise ValueError("customer access id must not be blank")
    entry = _frontend_dist(frontend_dist) / "customer" / "engagement" / "index.html"
    if entry.is_file():
        return entry.read_text(encoding="utf-8")
    return _build_fallback(
        "需求与方案中心",
        "客户需求确认、补充反馈与解决方案查看入口",
    )
