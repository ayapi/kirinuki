"""kirinuki clip コマンド定義"""

from pathlib import Path

import click
from pydantic import ValidationError

from kirinuki.cli.main import cli
from kirinuki.core.clip_service import ClipService
from kirinuki.core.clip_utils import parse_time_ranges, resolve_video_id
from kirinuki.core.errors import (
    AuthenticationRequiredError,
    InvalidURLError,
    VideoDownloadError,
)
from kirinuki.core.formatter import format_time_range
from kirinuki.infra.ffmpeg import FfmpegClientImpl
from kirinuki.infra.ytdlp_client import YtdlpClient
from kirinuki.models.clip import MultiClipRequest
from kirinuki.models.config import AppConfig


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

    try:
        request = MultiClipRequest(
            video_id=video_id,
            filename=filename,
            output_dir=output_dir,
            ranges=ranges,
        )
    except ValidationError as e:
        click.echo(f"エラー: リクエストが不正です: {e}", err=True)
        raise SystemExit(1) from e

    ytdlp = YtdlpClient(config)
    ffmpeg = FfmpegClientImpl()
    ffmpeg.check_available()
    service = ClipService(ytdlp_client=ytdlp, ffmpeg_client=ffmpeg)

    try:
        result = service.execute(request, on_progress=click.echo)
    except AuthenticationRequiredError as e:
        msg = "認証が必要です。`kirinuki cookie set` で設定してください"
        click.echo(f"エラー: {msg}: {e}", err=True)
        raise SystemExit(1) from e
    except VideoDownloadError as e:
        click.echo(f"エラー: {e}", err=True)
        raise SystemExit(1) from e

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
