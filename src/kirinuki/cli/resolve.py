"""チャンネルID自動解決ユーティリティ"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

import click

if TYPE_CHECKING:
    from kirinuki.models.domain import ChannelSummary


class HasListChannels(Protocol):
    def list_channels(self) -> list[ChannelSummary]: ...


def resolve_channel_id(
    channel_id: str | None,
    db: HasListChannels,
) -> str:
    """チャンネルIDを解決する。

    Args:
        channel_id: ユーザーが明示指定したチャンネルID。Noneの場合は自動解決を試みる。
        db: list_channels()メソッドを持つデータベースオブジェクト。

    Returns:
        解決されたチャンネルID。

    Raises:
        click.UsageError: チャンネルが未登録、または複数登録されている場合。
    """
    if channel_id is not None:
        return channel_id

    channels = db.list_channels()

    if len(channels) == 0:
        raise click.UsageError(
            "チャンネルが登録されていません。先に `kirinuki channel add <URL>` でチャンネルを登録してください。"
        )

    if len(channels) == 1:
        ch = channels[0]
        click.echo(
            f"デフォルトチャンネルを使用します: {ch.name} ({ch.channel_id})",
            err=True,
        )
        return ch.channel_id

    lines = ["複数のチャンネルが登録されています。チャンネルIDを指定してください:"]
    for ch in channels:
        lines.append(f"  - {ch.name} ({ch.channel_id})")
    raise click.UsageError("\n".join(lines))
