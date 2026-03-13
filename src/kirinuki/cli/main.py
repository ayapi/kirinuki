"""CLIメインエントリーポイント"""

import logging
from contextlib import contextmanager
from dataclasses import dataclass

import click

from kirinuki.core.channel_service import ChannelService
from kirinuki.core.clip_utils import build_youtube_url
from kirinuki.core.formatter import format_time, format_time_range
from kirinuki.core.search_service import SearchService
from kirinuki.core.segmentation_service import SegmentationService
from kirinuki.core.sync_service import SyncService
from kirinuki.infra.database import Database
from kirinuki.infra.embedding_provider import OpenAIEmbeddingProvider
from kirinuki.infra.llm_client import SEGMENT_PROMPT_VERSION, LlmClient
from kirinuki.infra.ytdlp_client import YtdlpClient
from kirinuki.cli.cookie import cookie as cookie_cmd
from kirinuki.cli.resolve import resolve_channel_id
from kirinuki.cli.suggest import suggest as suggest_cmd
from kirinuki.models.config import AppConfig
from kirinuki.models.domain import MatchType, SearchResult

_SNIPPET_MAX_LEN = 80


def _format_match_reason(r: SearchResult) -> str:
    """マッチ理由行をフォーマットする"""
    snippet = r.snippet
    if snippet and len(snippet) > _SNIPPET_MAX_LEN:
        snippet = snippet[:_SNIPPET_MAX_LEN] + "…"

    if r.match_type == MatchType.KEYWORD:
        return f"💬 キーワード | \"{snippet}\"" if snippet else "💬 キーワード"
    elif r.match_type == MatchType.SEMANTIC:
        pct = int((r.similarity or 0) * 100)
        return f"🔍 セマンティック | 類似度 {pct}%"
    elif r.match_type == MatchType.HYBRID:
        pct = int((r.similarity or 0) * 100)
        if snippet:
            return f"💬🔍 キーワード+セマンティック | \"{snippet}\" (類似度 {pct}%)"
        return f"💬🔍 キーワード+セマンティック | 類似度 {pct}%"
    return ""


@dataclass
class AppContext:
    config: AppConfig
    db: Database
    channel_service: ChannelService
    sync_service: SyncService
    segmentation_service: SegmentationService
    search_service: SearchService


@contextmanager
def create_app_context():
    config = AppConfig()
    db = Database(db_path=config.db_path, embedding_dimensions=config.embedding_dimensions)
    db.initialize()

    ytdlp = YtdlpClient(config)
    llm = LlmClient(config)
    embedding = OpenAIEmbeddingProvider(config)

    channel_svc = ChannelService(db=db, ytdlp_client=ytdlp)
    segmentation_svc = SegmentationService(
        db=db, llm_client=llm, embedding_provider=embedding,
        max_workers=config.max_concurrent_api_calls,
    )
    sync_svc = SyncService(
        db=db,
        ytdlp_client=ytdlp,
        segmentation_service=segmentation_svc,
        cookie_file_path=config.cookie_file_path,
    )
    search_svc = SearchService(db=db, embedding_provider=embedding)

    ctx = AppContext(
        config=config,
        db=db,
        channel_service=channel_svc,
        sync_service=sync_svc,
        segmentation_service=segmentation_svc,
        search_service=search_svc,
    )
    try:
        yield ctx
    finally:
        db.close()


@click.group()
def cli() -> None:
    """kirinuki - YouTube Live配信アーカイブの字幕蓄積・話題セグメンテーション・横断検索CLIツール"""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


@cli.group()
def channel() -> None:
    """チャンネルの登録・管理"""
    pass


@channel.command("add")
@click.argument("url")
def channel_add(url: str) -> None:
    """チャンネルを同期対象として登録する"""
    with create_app_context() as ctx:
        ch = ctx.channel_service.register(url)
        click.echo(f"チャンネルを登録しました: {ch.name} ({ch.channel_id})")


@channel.command("list")
def channel_list() -> None:
    """登録済みチャンネル一覧を表示する"""
    with create_app_context() as ctx:
        channels = ctx.channel_service.list_channels()
        if not channels:
            click.echo("登録済みチャンネルはありません")
            return
        for ch in channels:
            synced = ch.last_synced_at.strftime("%Y-%m-%d %H:%M") if ch.last_synced_at else "未同期"
            click.echo(
                f"  {ch.name} ({ch.channel_id})"
                f" - 動画: {ch.video_count}件 - 最終同期: {synced}"
            )


@channel.command("videos")
@click.argument("channel_id", default=None, required=False)
def channel_videos(channel_id: str | None) -> None:
    """チャンネルの同期済み動画一覧を表示する"""
    with create_app_context() as ctx:
        channel_id = resolve_channel_id(channel_id, ctx.db)
        videos = ctx.channel_service.list_videos(channel_id)
        if not videos:
            click.echo("同期済み動画はありません")
            return
        for v in videos:
            date = v.published_at.strftime("%Y-%m-%d") if v.published_at else "不明"
            duration_min = v.duration_seconds // 60
            click.echo(f"  [{date}] {v.title} ({duration_min}分) - {v.video_id}")


@cli.command()
@click.option("--max-segment-ms", default=300000, type=int, help="セグメント最大長(ms)")
def sync(max_segment_ms: int) -> None:
    """登録済みチャンネルの字幕を差分同期する"""
    with create_app_context() as ctx:
        click.echo("同期を開始します...")
        result = ctx.sync_service.sync_all(max_segment_ms=max_segment_ms)
        skip_detail = ""
        if result.skip_reasons:
            reason_labels = {
                "no_subtitle_available": "字幕なし",
                "no_target_language": "対象言語なし",
                "parse_failed": "パース失敗",
                "fetch_failed": "取得失敗",
                "not_live_archive": "配信アーカイブ以外",
            }
            parts = []
            for reason, count in result.skip_reasons.items():
                label = reason_labels.get(str(reason), str(reason))
                parts.append(f"{label}: {count}件")
            skip_detail = f" ({', '.join(parts)})"

        summary_parts = [
            f"取得済み {result.already_synced}件",
            f"新規 {result.newly_synced}件",
            f"スキップ {result.skipped}件{skip_detail}",
        ]
        if result.unavailable_skipped > 0:
            summary_parts.append(f"unavailableスキップ {result.unavailable_skipped}件")
        click.echo(f"同期完了: {' / '.join(summary_parts)}")
        if result.segmentation_retried > 0 or result.segmentation_retry_failed > 0:
            click.echo(
                f"セグメンテーション再試行: 成功 {result.segmentation_retried}件"
                f" / 失敗 {result.segmentation_retry_failed}件"
            )
        if result.errors:
            click.echo(f"エラー: {len(result.errors)}件")
            for err in result.errors:
                click.echo(f"  - {err.video_id}: {err.reason}")
        if result.auth_errors > 0:
            click.echo(
                f"メンバー限定動画の認証に失敗しました（{result.auth_errors}件）。"
                "Cookieを更新してください: kirinuki cookie set"
            )


@cli.command()
@click.argument("query")
@click.option("--limit", "-n", default=10, help="検索結果の最大件数")
@click.option("--video-id", multiple=True, default=(), help="絞り込む動画ID（複数指定可）")
@click.option("--tui", is_flag=True, default=False, help="TUIモードで結果を表示し、切り抜きを実行")
def search(query: str, limit: int, video_id: tuple[str, ...], tui: bool) -> None:
    """全動画を横断して検索する"""
    with create_app_context() as ctx:
        video_ids = list(video_id) if video_id else None
        results, warnings = ctx.search_service.search(query, limit=limit, video_ids=video_ids)
        for w in warnings:
            click.echo(f"警告: {w}", err=True)
        if not results:
            click.echo("該当する結果はありませんでした")
            return

        if tui:
            _run_tui_flow_search(results, ctx.config)
            return

        click.echo(f"検索結果: {len(results)}件\n")
        for i, r in enumerate(results, 1):
            time_range = format_time_range(r.start_time_ms / 1000, r.end_time_ms / 1000)
            click.echo(f"  {i}. [{r.channel_name}] {r.video_title}")
            click.echo(
                f"     {time_range}"
                f" | {r.summary}"
            )
            if r.match_type is not None:
                click.echo(f"     {_format_match_reason(r)}")
            click.echo(f"     {r.youtube_url}")
            click.echo()


@cli.command()
@click.argument("video_id")
@click.option("--tui", is_flag=True, default=False, help="TUIモードで結果を表示し、切り抜きを実行")
def segments(video_id: str, tui: bool) -> None:
    """動画の話題セグメント一覧を表示する"""
    with create_app_context() as ctx:
        segs = ctx.segmentation_service.list_segments(video_id)
        if not segs:
            click.echo("セグメントはありません")
            return

        if tui:
            _run_tui_flow_segments(segs, ctx.config)
            return

        click.echo(f"セグメント一覧 ({len(segs)}件):\n")
        for s in segs:
            time_range = format_time_range(s.start_ms / 1000, s.end_ms / 1000)
            url = build_youtube_url(video_id, s.start_ms)
            click.echo(
                f"  {time_range}"
                f" | {s.summary}"
            )
            click.echo(f"     {url}")



@cli.command()
@click.option("--video-id", default=None, help="特定の動画IDのみ再セグメンテーション")
@click.option("--max-segment-ms", default=300000, type=int, help="セグメント最大長（ミリ秒）")
@click.option("--force", is_flag=True, default=False, help="プロンプトバージョンに関わらず全動画を再処理")
def resegment(video_id: str | None, max_segment_ms: int, force: bool) -> None:
    """既存セグメントを削除して再セグメンテーションする"""
    with create_app_context() as ctx:
        if video_id:
            click.echo(f"動画 {video_id} を再セグメンテーションします...")
            segments = ctx.segmentation_service.resegment_video(
                video_id, max_segment_ms=max_segment_ms,
            )
            click.echo(f"完了: {len(segments)}セグメント生成")
        else:
            video_ids = ctx.db.get_resegment_target_video_ids()
            if not video_ids:
                click.echo("対象の動画はありません")
                return

            if not force:
                already_done = ctx.db.get_video_ids_with_segment_version(SEGMENT_PROMPT_VERSION)
                before_count = len(video_ids)
                video_ids = [vid for vid in video_ids if vid not in already_done]
                skipped = before_count - len(video_ids)
                if skipped > 0:
                    click.echo(
                        f"プロンプト{SEGMENT_PROMPT_VERSION}で処理済みの{skipped}動画をスキップ"
                    )

            if not video_ids:
                click.echo("対象の動画はありません")
                return
            click.echo(f"全{len(video_ids)}動画を再セグメンテーションします...")
            for i, vid in enumerate(video_ids, 1):
                click.echo(f"({i}/{len(video_ids)}) {vid}...")
                try:
                    segments = ctx.segmentation_service.resegment_video(
                        vid, max_segment_ms=max_segment_ms,
                    )
                    click.echo(f"  → {len(segments)}セグメント生成")
                except Exception as e:
                    click.echo(f"  → エラー: {e}")
            click.echo("再セグメンテーション完了")


@cli.group()
def unavailable() -> None:
    """unavailable動画の記録管理"""
    pass


@unavailable.command("reset")
@click.option("--channel", "channel_id", default=None, help="特定チャンネルのみリセット")
def unavailable_reset(channel_id: str | None) -> None:
    """unavailable記録をリセットする"""
    if channel_id is None:
        if not click.confirm("全チャンネルのunavailable記録をリセットしますか？"):
            raise SystemExit(1)
    with create_app_context() as ctx:
        cleared = ctx.db.clear_all_unavailable(channel_id)
        click.echo(f"unavailable記録を{cleared}件リセットしました。")


def _run_tui_flow_search(results: list, config: AppConfig) -> None:
    """search結果のTUIフロー共通処理"""
    from kirinuki.cli.tui import (
        adapt_search_results,
        execute_clips,
        run_tui_select,
    )

    candidates = adapt_search_results(results)
    if not candidates:
        click.echo("TUI表示可能な結果がありません")
        return
    _run_tui_clip_flow(candidates, config)


def _run_tui_flow_segments(segs: list, config: AppConfig) -> None:
    """segments結果のTUIフロー共通処理"""
    from kirinuki.cli.tui import adapt_segments

    candidates = adapt_segments(segs)
    if not candidates:
        click.echo("TUI表示可能な結果がありません")
        return
    _run_tui_clip_flow(candidates, config)


def _run_tui_clip_flow(candidates: list, config: AppConfig) -> None:
    """TUI選択→切り抜き実行の共通フロー"""
    from kirinuki.cli.factory import create_clip_service
    from kirinuki.cli.tui import execute_clips, run_tui_select

    selected = run_tui_select(candidates)
    if not selected:
        click.echo("キャンセルしました")
        return

    clip_service = create_clip_service(config)
    outcomes = execute_clips(
        selected, clip_service, config.output_dir, on_progress=click.echo
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


@cli.group()
def migrate() -> None:
    """データベースマイグレーション"""
    pass


@migrate.command("backfill-broadcast-start")
def backfill_broadcast_start() -> None:
    """既存動画の配信開始日時を一括取得・更新する"""
    with create_app_context() as ctx:
        videos = ctx.db.get_videos_without_broadcast_start()
        if not videos:
            click.echo("対象の動画はありません")
            return

        click.echo(f"配信開始日時が未設定の動画: {len(videos)}件")

        updated = 0
        skipped = 0
        errors = 0

        ytdlp = YtdlpClient(ctx.config)

        for i, video in enumerate(videos, 1):
            video_id = video["video_id"]
            click.echo(f"({i}/{len(videos)}) {video['title']}...", nl=False)
            try:
                meta = ytdlp.fetch_video_metadata(video_id)
                if meta.broadcast_start_at is not None:
                    ctx.db.update_broadcast_start_at(video_id, meta.broadcast_start_at)
                    click.echo(" 更新")
                    updated += 1
                else:
                    # フォールバック: published_at を使用
                    published_at_str = video.get("published_at")
                    if published_at_str:
                        from datetime import datetime
                        fallback = datetime.fromisoformat(published_at_str)
                        ctx.db.update_broadcast_start_at(video_id, fallback)
                        click.echo(" 更新 (published_atで代替)")
                        updated += 1
                    else:
                        click.echo(" スキップ (日時情報なし)")
                        skipped += 1
            except Exception as e:
                click.echo(f" エラー: {e}")
                errors += 1

        click.echo(f"\n完了: 更新 {updated}件 / スキップ {skipped}件 / エラー {errors}件")


@cli.command()
@click.option("--count", default=20, show_default=True, help="表示件数")
@click.option("--tui", is_flag=True, default=False, help="TUIモードで動画を選択し、segments/suggestを実行")
def videos(count: int, tui: bool) -> None:
    """全チャンネル横断で動画一覧を表示する"""
    with create_app_context() as ctx:
        all_videos = ctx.db.get_all_videos(count=count)
        if not all_videos:
            click.echo("動画が登録されていません")
            return

        if tui:
            _run_tui_flow_videos(all_videos, ctx)
            return

        for v in all_videos:
            date = v.published_at.strftime("%Y-%m-%d %H:%M") if v.published_at else "不明"
            url = f"https://www.youtube.com/watch?v={v.video_id}"
            click.echo(f"  [{date}] {v.title}")
            click.echo(f"     {url}")


def _run_tui_flow_videos(all_videos: list, ctx: AppContext) -> None:
    """videos TUIモード: 動画選択 → 操作選択 → 既存TUIフロー実行"""
    from kirinuki.cli.tui import run_tui_select_one

    options = [
        f"[{v.published_at.strftime('%Y-%m-%d %H:%M') if v.published_at else '不明'}] {v.title}"
        for v in all_videos
    ]
    selected_idx = run_tui_select_one(options)
    if selected_idx is None:
        click.echo("キャンセルしました")
        return

    selected_video = all_videos[selected_idx]
    video_id = selected_video.video_id

    # 操作選択メニュー
    action_idx = run_tui_select_one(["segments - 話題セグメント一覧", "suggest - 切り抜き候補推薦"])
    if action_idx is None:
        click.echo("キャンセルしました")
        return

    if action_idx == 0:
        # segments
        segs = ctx.segmentation_service.list_segments(video_id)
        if not segs:
            click.echo("セグメントはありません")
            return
        _run_tui_flow_segments(segs, ctx.config)
    else:
        # suggest
        from kirinuki.core.suggest import SuggestService
        from kirinuki.infra.llm_client import LlmClient
        from kirinuki.models.recommendation import SuggestOptions

        llm = LlmClient(ctx.config)
        service = SuggestService(db=ctx.db, llm=llm)
        options = SuggestOptions(video_ids=[video_id], count=1, threshold=1)
        result = service.suggest(options)

        if not result.videos:
            click.echo("推薦候補はありません")
            return

        from kirinuki.cli.suggest import _run_tui_flow_suggest

        _run_tui_flow_suggest(result, ctx.config)


cli.add_command(cookie_cmd, "cookie")
cli.add_command(suggest_cmd, "suggest")

import kirinuki.cli.clip  # noqa: E402, F401  clip コマンド登録


if __name__ == "__main__":
    cli()
