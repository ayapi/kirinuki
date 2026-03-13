"""TUIインタラクティブ選択モジュール。

search/segments/suggestの結果をインタラクティブなメニューで表示し、
ユーザーが選択した候補を返す。
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import click

from kirinuki.core.clip_utils import extract_video_id, generate_clip_filename
from kirinuki.core.formatter import format_time_range
from kirinuki.models.clip import ClipOutcome, MultiClipRequest, TimeRange
from kirinuki.models.domain import MatchType, SearchResult, Segment
from kirinuki.models.recommendation import SuggestResult
from kirinuki.models.tui import ClipCandidate


def adapt_search_results(results: list[SearchResult]) -> list[ClipCandidate]:
    """SearchResult一覧をClipCandidate一覧に変換する。"""
    candidates: list[ClipCandidate] = []
    for r in results:
        try:
            video_id = extract_video_id(r.youtube_url)
        except Exception:
            continue

        time_range = format_time_range(r.start_time_ms / 1000, r.end_time_ms / 1000)
        match_label = r.match_type.value if r.match_type else ""
        label = f"[{r.score:.2f} {match_label}] {r.video_title} | {time_range} {r.summary}"

        candidates.append(
            ClipCandidate(
                video_id=video_id,
                start_ms=r.start_time_ms,
                end_ms=r.end_time_ms,
                summary=r.summary,
                display_label=label,
                video_title=r.video_title,
                channel_name=r.channel_name,
                score=r.score,
                match_type=r.match_type.value if r.match_type else None,
            )
        )
    return candidates


def adapt_segments(segments: list[Segment]) -> list[ClipCandidate]:
    """Segment一覧をClipCandidate一覧に変換する。"""
    candidates: list[ClipCandidate] = []
    for s in segments:
        time_range = format_time_range(s.start_ms / 1000, s.end_ms / 1000)
        label = f"{time_range} {s.summary}"
        candidates.append(
            ClipCandidate(
                video_id=s.video_id,
                start_ms=s.start_ms,
                end_ms=s.end_ms,
                summary=s.summary,
                display_label=label,
            )
        )
    return candidates


def adapt_suggest_results(result: SuggestResult) -> list[ClipCandidate]:
    """SuggestResultをClipCandidate一覧に変換する。"""
    candidates: list[ClipCandidate] = []
    for video in result.videos:
        for rec in video.recommendations:
            start_ms = int(rec.start_time * 1000)
            end_ms = int(rec.end_time * 1000)
            time_range = format_time_range(rec.start_time, rec.end_time)
            label = f"[{rec.score}/10] {video.title} | {time_range} {rec.summary}"
            candidates.append(
                ClipCandidate(
                    video_id=rec.video_id,
                    start_ms=start_ms,
                    end_ms=end_ms,
                    summary=rec.summary,
                    display_label=label,
                    video_title=video.title,
                    recommend_score=rec.score,
                    appeal=rec.appeal,
                )
            )
    return candidates


def run_tui_select_one(options: list[str]) -> int | None:
    """単一選択メニューを表示し、選択されたインデックスを返す。キャンセル時はNone。"""
    import shutil

    from beaupy import select

    terminal_height = shutil.get_terminal_size().lines
    page_size = max(5, terminal_height - 4)

    try:
        selected = select(
            options,
            return_index=True,
            pagination=True,
            page_size=page_size,
        )
    except KeyboardInterrupt:
        return None

    return selected


def run_tui_select(candidates: list[ClipCandidate]) -> list[ClipCandidate]:
    """マルチセレクトメニューを表示し、選択された候補を返す。

    キャンセル時（Ctrl+C/Esc）は空リストを返す。
    """
    import shutil

    from beaupy import select_multiple

    options = [c.display_label for c in candidates]
    terminal_height = shutil.get_terminal_size().lines
    page_size = max(5, terminal_height - 4)

    try:
        selected_indices = select_multiple(
            options,
            return_indices=True,
            pagination=True,
            page_size=page_size,
        )
    except KeyboardInterrupt:
        return []

    if not selected_indices:
        return []

    return [candidates[i] for i in selected_indices]


def execute_clips(
    selected: list[ClipCandidate],
    clip_service: object,
    output_dir: Path,
    on_progress: Callable[[str], None] | None = None,
) -> list[ClipOutcome]:
    """選択された候補を順次切り抜き実行する。

    同じ動画IDの候補はグルーピングし、動画を1回だけダウンロードする。
    KeyboardInterrupt時は処理済み結果を返す。
    """
    if not selected:
        return []

    def _notify(msg: str) -> None:
        if on_progress:
            on_progress(msg)

    total = len(selected)
    outcomes: list[ClipOutcome] = []
    interrupted = False

    # video_id でグルーピング（出現順を保持）
    groups: dict[str, list[ClipCandidate]] = {}
    for candidate in selected:
        groups.setdefault(candidate.video_id, []).append(candidate)

    done = 0

    for video_id, candidates in groups.items():
        if interrupted:
            break

        # TimeRange とファイル名を準備
        group_ranges: list[TimeRange] = []
        group_filenames: list[str] = []

        for candidate in candidates:
            start_sec = candidate.start_ms / 1000
            end_sec = candidate.end_ms / 1000
            try:
                time_range = TimeRange(
                    start_seconds=start_sec,
                    end_seconds=end_sec,
                )
            except Exception:
                done += 1
                _notify(
                    f"[{done}/{total}] スキップ（時間範囲が不正: "
                    f"start_ms={candidate.start_ms}, end_ms={candidate.end_ms}）: "
                    f"{candidate.summary[:40]}"
                )
                continue

            filename = generate_clip_filename(
                candidate.video_id, candidate.start_ms, candidate.summary
            )
            group_ranges.append(time_range)
            group_filenames.append(filename)

        if not group_ranges:
            continue

        clip_count = len(group_ranges)
        if clip_count == 1:
            _notify(
                f"[{done + 1}/{total}] 切り抜き中: "
                f"{candidates[0].summary[:40]}..."
            )
        else:
            _notify(
                f"[{done + 1}-{done + clip_count}/{total}] "
                f"動画 {video_id} から {clip_count}件 切り抜き中..."
            )

        request = MultiClipRequest(
            video_id=video_id,
            output_dir=output_dir,
            ranges=group_ranges,
            filenames=group_filenames,
        )

        try:
            result = clip_service.execute(request, on_progress=None)
            outcomes.extend(result.outcomes)
        except KeyboardInterrupt:
            _notify(f"\n中断しました（{done}/{total}件完了）")
            interrupted = True
        except Exception as e:
            for tr in group_ranges:
                outcomes.append(
                    ClipOutcome(
                        range=tr,
                        output_path=None,
                        error=str(e),
                    )
                )

        done += clip_count

    return outcomes


def create_clip_service(config: object) -> object:
    """AppConfigからClipServiceを生成する共通ヘルパー。

    .. deprecated::
        ``kirinuki.cli.factory.create_clip_service`` を使用してください。
    """
    from kirinuki.cli.factory import create_clip_service as _factory

    return _factory(config)
