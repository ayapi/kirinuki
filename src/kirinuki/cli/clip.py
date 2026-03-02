"""kirinuki clip コマンド定義"""

import click
from pydantic import ValidationError

from kirinuki.cli.main import cli
from kirinuki.core.clip_service import ClipService
from kirinuki.core.clip_utils import parse_time_str, resolve_video_id
from kirinuki.core.errors import (
    AuthenticationRequiredError,
    ClipError,
    FfmpegNotFoundError,
    InvalidURLError,
    VideoDownloadError,
)
from kirinuki.core.formatter import format_time
from kirinuki.infra.ffmpeg import FfmpegClientImpl
from kirinuki.infra.ytdlp_client import YtdlpClient
from kirinuki.models.clip import ClipRequest
from kirinuki.models.config import AppConfig

from pathlib import Path


@cli.command()
@click.argument("video")
@click.argument("start")
@click.argument("end")
@click.argument("output", type=click.Path())
def clip(video: str, start: str, end: str, output: str) -> None:
    """動画の指定区間を切り抜く"""
    try:
        video_id = resolve_video_id(video)
    except InvalidURLError as e:
        click.echo(f"エラー: 無効な動画ID/URLです: {e}", err=True)
        raise SystemExit(1)

    try:
        start_seconds = parse_time_str(start)
        end_seconds = parse_time_str(end)
    except ValueError as e:
        click.echo(f"エラー: 時間範囲が不正です: {e}", err=True)
        raise SystemExit(1)

    output_path = Path(output)

    try:
        request = ClipRequest(
            url=video_id,
            start_seconds=start_seconds,
            end_seconds=end_seconds,
            output_path=output_path,
        )
    except ValidationError as e:
        click.echo(f"エラー: 時間範囲が不正です: {e}", err=True)
        raise SystemExit(1)

    config = AppConfig()
    ytdlp = YtdlpClient(config)
    ffmpeg = FfmpegClientImpl()
    service = ClipService(ytdlp_client=ytdlp, ffmpeg_client=ffmpeg)

    try:
        result = service.execute(request, on_progress=click.echo)
    except FfmpegNotFoundError as e:
        click.echo(f"エラー: {e}", err=True)
        raise SystemExit(1)
    except VideoDownloadError as e:
        click.echo(f"エラー: {e}", err=True)
        raise SystemExit(1)
    except AuthenticationRequiredError as e:
        click.echo(f"エラー: 認証が必要です。`kirinuki cookie set` で設定してください: {e}", err=True)
        raise SystemExit(1)
    except ClipError as e:
        click.echo(f"エラー: {e}", err=True)
        raise SystemExit(1)
    except FileNotFoundError as e:
        click.echo(f"エラー: 出力先ディレクトリが存在しません: {e}", err=True)
        raise SystemExit(1)

    start_str = format_time(result.start_seconds)
    end_str = format_time(result.end_seconds)
    click.echo(f"切り抜き完了: {result.output_path} ({start_str} - {end_str})")
