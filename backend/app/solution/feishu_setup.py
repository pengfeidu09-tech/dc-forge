"""Operator CLI for DCForge Feishu QR setup and long-connection startup."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from backend.app.solution.feishu_bot import FeishuBotConfig
from backend.app.solution.feishu_registration import (
    FeishuAppRegistration,
    FeishuRegistrationError,
    FeishuRegistrationResult,
    persist_feishu_credentials,
)
from backend.app.solution.feishu_ws import run_feishu_websocket


def _load_env(path: Path) -> None:
    try:
        from dotenv import load_dotenv
    except ImportError as error:
        raise RuntimeError("Loading .env requires python-dotenv") from error
    load_dotenv(path, override=False)


def _print_qr(url: str) -> None:
    try:
        import qrcode
    except ImportError as error:
        raise RuntimeError("QR setup requires the qrcode package") from error
    code = qrcode.QRCode(border=4)
    code.add_data(url)
    code.make(fit=True)
    code.print_ascii(tty=sys.stdout.isatty(), invert=True)


def _config_from_result(result: FeishuRegistrationResult) -> FeishuBotConfig:
    api_url = (
        "https://open.larksuite.com"
        if result.domain == "lark"
        else "https://open.feishu.cn"
    )
    return FeishuBotConfig(
        app_id=result.app_id,
        app_secret=result.app_secret,
        allowed_open_id=result.open_id,
        api_base_url=api_url,
    )


def setup(env_path: Path, *, listen: bool = False) -> None:
    _load_env(env_path)
    registration = FeishuAppRegistration(domain="feishu")
    registration.initialize()
    begin = registration.begin()

    print("请使用飞书手机客户端扫描下面的二维码创建 DCForge 个人机器人：")
    _print_qr(begin.qr_url)
    print(f"如果二维码无法识别，请在浏览器打开：{begin.qr_url}")
    print(f"授权码：{begin.user_code}")
    print("等待飞书授权……")

    result = registration.poll(
        device_code=begin.device_code,
        interval=begin.interval,
        expire_in=begin.expire_in,
    )
    saved_path = persist_feishu_credentials(result, env_path)
    print(f"飞书个人机器人已创建，凭证已安全写入 {saved_path}")
    print(f"App ID: {result.app_id}")
    if result.open_id:
        print("已默认限制为仅扫码账号可与机器人私聊。")

    if listen:
        print("正在启动飞书长连接……")
        run_feishu_websocket(_config_from_result(result))


def listen(env_path: Path) -> None:
    _load_env(env_path)
    print("正在启动 DCForge 飞书长连接，按 Ctrl+C 停止。")
    run_feishu_websocket(
        FeishuBotConfig.from_env(require_verification_token=False)
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create and run DCForge's Feishu personal bot"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    setup_parser = subparsers.add_parser(
        "setup", help="scan a QR code to create a Feishu personal bot"
    )
    setup_parser.add_argument("--env-file", default=".env")
    setup_parser.add_argument(
        "--listen", action="store_true", help="start the long connection after setup"
    )

    listen_parser = subparsers.add_parser(
        "listen", help="start the Feishu long connection from existing credentials"
    )
    listen_parser.add_argument("--env-file", default=".env")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    env_path = Path(args.env_file).expanduser()
    try:
        if args.command == "setup":
            setup(env_path, listen=args.listen)
        else:
            listen(env_path)
    except KeyboardInterrupt:
        print("\n飞书长连接已停止。")
        return 130
    except (FeishuRegistrationError, RuntimeError) as error:
        print(f"飞书机器人操作失败：{error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

