"""CLIメインエントリーポイント"""

import logging
from contextlib import contextmanager
from dataclasses import dataclass

import click

from kirinuki.core.channel_service import ChannelService
from kirinuki.core.clip_utils import build_youtube_url
from kirinuki.core.search_service import SearchService
from kirinuki.core.segmentation_service import SegmentationService
from kirinuki.core.sync_service import SyncService
from kirinuki.infra.database import Database
from kirinuki.infra.embedding_provider import OpenAIEmbeddingProvider
from kirinuki.infra.llm_client import LlmClient
from kirinuki.infra.ytdlp_client import YtdlpClient
from kirinuki.cli.cookie import cookie as cookie_cmd
from kirinuki.cli.resolve import resolve_channel_id
from kirinuki.cli.suggest import suggest as suggest_cmd
from kirinuki.models.config import AppConfig


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
    segmentation_svc = SegmentationService(db=db, llm_client=llm, embedding_provider=embedding)
    sync_svc = SyncService(db=db, ytdlp_client=ytdlp, segmentation_service=segmentation_svc)
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
def sync() -> None:
    """登録済みチャンネルの字幕を差分同期する"""
    with create_app_context() as ctx:
        click.echo("同期を開始します...")
        result = ctx.sync_service.sync_all()
        click.echo(
            f"同期完了: 取得済み {result.already_synced}件"
            f" / 新規 {result.newly_synced}件"
            f" / スキップ {result.skipped}件"
        )
        if result.errors:
            click.echo(f"エラー: {len(result.errors)}件")
            for err in result.errors:
                click.echo(f"  - {err.video_id}: {err.reason}")


@cli.command()
@click.argument("query")
@click.option("--limit", "-n", default=10, help="検索結果の最大件数")
def search(query: str, limit: int) -> None:
    """全動画を横断して検索する"""
    with create_app_context() as ctx:
        results = ctx.search_service.search(query, limit=limit)
        if not results:
            click.echo("該当する結果はありませんでした")
            return
        click.echo(f"検索結果: {len(results)}件\n")
        for i, r in enumerate(results, 1):
            start_min = r.start_time_ms // 60000
            start_sec = (r.start_time_ms % 60000) // 1000
            end_min = r.end_time_ms // 60000
            end_sec = (r.end_time_ms % 60000) // 1000
            click.echo(f"  {i}. [{r.channel_name}] {r.video_title}")
            click.echo(
                f"     {start_min:02d}:{start_sec:02d} - {end_min:02d}:{end_sec:02d}"
                f" | {r.summary}"
            )
            click.echo(f"     {r.youtube_url}")
            click.echo()


@cli.command()
@click.argument("video_id")
def segments(video_id: str) -> None:
    """動画の話題セグメント一覧を表示する"""
    with create_app_context() as ctx:
        segs = ctx.segmentation_service.list_segments(video_id)
        if not segs:
            click.echo("セグメントはありません")
            return
        click.echo(f"セグメント一覧 ({len(segs)}件):\n")
        for s in segs:
            start_min = s.start_ms // 60000
            start_sec = (s.start_ms % 60000) // 1000
            end_min = s.end_ms // 60000
            end_sec = (s.end_ms % 60000) // 1000
            url = build_youtube_url(video_id, s.start_ms)
            click.echo(
                f"  {start_min:02d}:{start_sec:02d} - {end_min:02d}:{end_sec:02d}"
                f" | {s.summary}"
            )
            click.echo(f"     {url}")



cli.add_command(cookie_cmd, "cookie")
cli.add_command(suggest_cmd, "suggest")


if __name__ == "__main__":
    cli()
