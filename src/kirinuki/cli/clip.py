"""kirinuki clip コマンド定義"""

import logging
import sys
from datetime import datetime
from pathlib import Path

import click
from pydantic import ValidationError

from kirinuki.cli.factory import create_clip_service
from kirinuki.cli.main import cli
from kirinuki.cli.progress_renderer import ProgressRenderer
from kirinuki.core.clip_utils import parse_time_ranges, resolve_video_id
from kirinuki.core.errors import (
    AuthenticationRequiredError,
    InvalidURLError,
    VideoDownloadError,
)
from kirinuki.core.formatter import format_time_range
from kirinuki.models.clip import MultiClipRequest
from kirinuki.models.config import AppConfig

logger = logging.getLogger(__name__)


def _fetch_broadcast_start_at(
    config: AppConfig, video_id: str,
) -> datetime | None:
    """メタデータから broadcast_start_at を取得する。失敗時は None。"""
    from kirinuki.infra.ytdlp_client import YtdlpClient

    ytdlp = YtdlpClient(config)
    meta = ytdlp.fetch_video_metadata(video_id)
    return meta.broadcast_start_at or meta.published_at


@cli.command()
@click.argument("video")
@click.argument("filename")
@click.argument("time_ranges")
@click.option(
    "--output-dir", "output_dir_str", default=None,
    type=click.Path(), help="出力先ディレクトリ",
)
def clip(
    video: str, filename: str, time_ranges: str,
    output_dir_str: str | None,
) -> None:
    """動画の指定区間を切り抜く

    \b
    VIDEO: 動画IDまたはYouTube URL
    FILENAME: 出力ファイル名 (例: output.mp4)
    TIME_RANGES: 時間範囲 (例: 18:03-19:31,21:31-23:20)
    """
    try:
        video_id = resolve_video_id(video)
    except InvalidURLError as e:
        click.echo(f"エラー: 無効な動画ID/URLです: {e}", err=True)
        raise SystemExit(1) from e

    try:
        ranges = parse_time_ranges(time_ranges)
    except ValueError as e:
        click.echo(f"エラー: 時間範囲が不正です: {e}", err=True)
        raise SystemExit(1) from e

    config = AppConfig()
    output_dir = Path(output_dir_str) if output_dir_str else config.output_dir

    # メタデータ取得で broadcast_start_at を取得
    broadcast_start_at: datetime | None = None
    try:
        broadcast_start_at = _fetch_broadcast_start_at(config, video_id)
    except Exception as e:
        logger.warning("メタデータ取得に失敗しました: %s", e)
        click.echo(
            f"警告: メタデータ取得に失敗しました（日時プレフィックスなしで続行）: {e}",
            err=True,
        )

    try:
        request = MultiClipRequest(
            video_id=video_id,
            filename=filename,
            output_dir=output_dir,
            ranges=ranges,
            broadcast_start_at=broadcast_start_at,
        )
    except ValidationError as e:
        click.echo(f"エラー: リクエストが不正です: {e}", err=True)
        raise SystemExit(1) from e

    service = create_clip_service(config)
    renderer = ProgressRenderer(total=len(ranges), output=sys.stderr)

    try:
        result = service.execute(request, on_progress=renderer.update)
    except AuthenticationRequiredError as e:
        msg = "認証が必要です。`kirinuki cookie set` で設定してください"
        click.echo(f"エラー: {msg}: {e}", err=True)
        raise SystemExit(1) from e
    except VideoDownloadError as e:
        click.echo(f"エラー: {e}", err=True)
        raise SystemExit(1) from e
    finally:
        renderer.finish()

    # サマリー表示
    click.echo()
    click.echo(
        f"完了: 成功 {result.success_count}件"
        f" / 失敗 {result.failure_count}件"
    )
    for outcome in result.outcomes:
        if outcome.output_path is not None:
            time_range = format_time_range(outcome.range.start_seconds, outcome.range.end_seconds)
            click.echo(
                f"  {outcome.output_path} ({time_range})"
            )

    if result.failure_count > 0:
        for outcome in result.outcomes:
            if outcome.error is not None:
                time_range = format_time_range(outcome.range.start_seconds, outcome.range.end_seconds)
                click.echo(
                    f"  失敗 ({time_range}): {outcome.error}"
                )
