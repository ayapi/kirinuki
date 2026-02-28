"""Cookie管理CLIコマンド"""

import sys

import click

from kirinuki.core.cookie_service import CookieService


@click.group()
def cookie() -> None:
    """Cookieの管理（設定・確認・削除）"""
    pass


@cookie.command("set")
def cookie_set() -> None:
    """cookiesの内容を標準入力から読み取り保存する"""
    if sys.stdin.isatty():
        click.echo("cookiesの内容をペーストしてください（完了: Ctrl+D / Windows: Ctrl+Z → Enter）:")

    content = click.get_text_stream("stdin").read()

    service = CookieService()
    try:
        service.save(content)
    except ValueError as e:
        click.echo(f"エラー: {e}", err=True)
        raise SystemExit(1)

    click.echo("cookiesを保存しました。")


@cookie.command("status")
def cookie_status() -> None:
    """cookiesの設定状態を確認する"""
    service = CookieService()
    status = service.status()

    if status.exists:
        assert status.updated_at is not None
        updated = status.updated_at.astimezone().strftime("%Y-%m-%d %H:%M:%S")
        click.echo(f"cookies: 設定済み（最終更新: {updated}）")
    else:
        click.echo("cookies: 未設定")


@cookie.command("delete")
def cookie_delete() -> None:
    """保存済みのcookiesを削除する"""
    if not click.confirm("cookiesを削除しますか？"):
        raise SystemExit(1)

    service = CookieService()
    try:
        service.delete()
    except FileNotFoundError as e:
        click.echo(f"エラー: {e}", err=True)
        raise SystemExit(1)

    click.echo("cookiesを削除しました。")
