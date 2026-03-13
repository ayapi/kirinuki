"""suggest サブコマンド"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import click

from kirinuki.cli.resolve import resolve_channel_id
from kirinuki.core.errors import ChannelNotFoundError, NoArchivesError
from kirinuki.core.formatter import RecommendationFormatter, format_broadcast_date
from kirinuki.core.suggest import SuggestService
from kirinuki.infra.database import Database
from kirinuki.infra.llm_client import LlmClient
from kirinuki.models.config import AppConfig
from kirinuki.models.recommendation import SuggestOptions


def parse_until_datetime(value: str) -> datetime:
    """'YYYY-MM-DD' または 'YYYY-MM-DD HH:MM' を datetime に変換する。

    日付のみの場合は 23:59:59 として扱う（その日の配信をすべて含む）。
    パース失敗時は click.BadParameter を送出する。
    """
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(value, fmt)
            if fmt == "%Y-%m-%d":
                dt = dt.replace(hour=23, minute=59, second=59)
            return dt
        except ValueError:
            continue
    raise click.BadParameter(
        "無効な日時形式です。YYYY-MM-DD または YYYY-MM-DD HH:MM を指定してください"
    )


def get_db_path() -> Path:
    """DB パスを取得する（テスト時にモック差し替え可能）"""
    config = AppConfig()
    return config.db_path


def _status(msg: str, is_json: bool) -> None:
    """進捗メッセージを stderr に出力する"""
    if not is_json:
        click.echo(msg, err=True)


@click.command()
@click.argument("channel", default=None, required=False)
@click.option("--count", default=3, show_default=True, help="対象アーカイブ件数")
@click.option("--threshold", default=7, show_default=True, help="推薦スコア閾値（1〜10）")
@click.option("--json", "output_json", is_flag=True, default=False, help="JSON形式で出力")
@click.option("--tui", is_flag=True, default=False, help="TUIモードで結果を表示し、切り抜きを実行")
@click.option("--video-id", multiple=True, default=(), help="絞り込む動画ID（複数指定可）")
@click.option("--until", "until_str", default=None, help="配信開始日時の上限（YYYY-MM-DD または YYYY-MM-DD HH:MM）")
def suggest(
    channel: str | None,
    count: int,
    threshold: int,
    output_json: bool,
    tui: bool,
    video_id: tuple[str, ...],
    until_str: str | None,
) -> None:
    """チャンネルの最新アーカイブから切り抜き候補を推薦する。

    CHANNEL: チャンネルID（例: UC...）。省略時は登録チャンネルが1つなら自動選択。
    --video-id 指定時は CHANNEL を省略できます。
    """
    db_path = get_db_path()
    config = AppConfig()
    db = Database(db_path=db_path, embedding_dimensions=config.embedding_dimensions)

    try:
        try:
            db.initialize()
        except Exception as e:
            click.echo(f"エラー: データベースの初期化に失敗しました: {e}", err=True)
            sys.exit(1)

        llm = LlmClient(config)

        video_ids = list(video_id) if video_id else None

        until = None
        if until_str is not None:
            until = parse_until_datetime(until_str)

        if video_ids:
            options = SuggestOptions(video_ids=video_ids, count=count, threshold=threshold, until=until)
        else:
            channel = resolve_channel_id(channel, db)
            options = SuggestOptions(channel_id=channel, count=count, threshold=threshold, until=until)

        service = SuggestService(db=db, llm=llm)
        formatter = RecommendationFormatter()

        _status("対象動画を選定中...", output_json)

        # まず動画一覧を取得して表示
        if video_ids:
            videos = db.get_videos_by_ids(video_ids)
        else:
            videos = db.get_latest_videos(channel, count, until=until)
        if videos:
            _status(f"\n対象アーカイブ ({len(videos)}件):", output_json)
            for v in videos:
                _status(f"  - {v['title']} ({format_broadcast_date(v.get('broadcast_start_at', ''))})", output_json)
            _status("", output_json)

        _status("セグメントを評価中...", output_json)
        result = service.suggest(options)

        # 警告メッセージをstderrに出力
        for w in result.warnings:
            click.echo(f"警告: {w}", err=True)

        if not result.videos:
            msg = (
                f"推薦候補: 0件（全{result.total_candidates}件中、閾値{threshold}以上の候補なし）\n"
                f"閾値を下げて再実行してください（例: --threshold {max(1, threshold - 2)}）"
            )
            if output_json:
                click.echo(formatter.format_json(result))
            else:
                click.echo(msg)
            return

        if tui:
            _run_tui_flow_suggest(result, config)
            return

        _status("結果を表示中...\n", output_json)

        if output_json:
            click.echo(formatter.format_json(result))
        else:
            click.echo(formatter.format_text(result))

    except NoArchivesError as e:
        click.echo(f"エラー: {e}", err=True)
        sys.exit(1)
    except ChannelNotFoundError as e:
        click.echo(f"エラー: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"エラー: 予期しないエラーが発生しました: {e}", err=True)
        sys.exit(1)
    finally:
        db.close()


def _run_tui_flow_suggest(result: object, config: AppConfig) -> None:
    """suggest結果のTUIフロー処理"""
    from kirinuki.cli.factory import create_clip_service
    from kirinuki.cli.tui import (
        adapt_suggest_results,
        execute_clips,
        run_tui_select,
    )
    from kirinuki.infra.ytdlp_client import YtdlpClient

    candidates = adapt_suggest_results(result)
    if not candidates:
        click.echo("TUI表示可能な結果がありません")
        return

    selected = run_tui_select(candidates)
    if not selected:
        click.echo("キャンセルしました")
        return

    clip_service = create_clip_service(config)
    ytdlp = YtdlpClient(config)
    outcomes = execute_clips(
        selected, clip_service, config.output_dir, on_progress=click.echo,
        ytdlp_client=ytdlp,
    )

    # サマリー表示
    success = sum(1 for o in outcomes if o.output_path is not None)
    failure = sum(1 for o in outcomes if o.output_path is None)
    click.echo()
    click.echo(f"完了: 成功 {success}件 / 失敗 {failure}件")
    for o in outcomes:
        if o.output_path is not None:
            click.echo(f"  {o.output_path}")
    for o in outcomes:
        if o.error is not None:
            from kirinuki.core.formatter import format_time_range as fmt_tr

            tr = fmt_tr(o.range.start_seconds, o.range.end_seconds)
            click.echo(f"  失敗 ({tr}): {o.error}")
