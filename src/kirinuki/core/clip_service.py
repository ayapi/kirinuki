"""切り抜きオーケストレーションサービス"""

import logging
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Protocol

from kirinuki.core.clip_utils import build_numbered_filename, prepend_datetime_prefix
from kirinuki.core.errors import AuthenticationRequiredError
from kirinuki.models.clip import (
    ClipOutcome,
    ClipPhase,
    ClipProgress,
    MultiClipRequest,
    MultiClipResult,
)

logger = logging.getLogger(__name__)

DEFAULT_CLIP_MARGIN_SECONDS: float = 5.0


class _FfmpegClient(Protocol):
    def reencode(self, file_path: Path) -> None: ...


def _convert_ytdlp_progress(index: int, d: dict) -> ClipProgress | None:
    """yt-dlpのprogress_hooks dictをClipProgressに変換する。

    finishedステータスはダウンロードフェーズの完了を示す中間状態のため無視する。
    """
    status = d.get("status")
    if status != "downloading":
        return None

    downloaded = d.get("downloaded_bytes", 0)
    total = d.get("total_bytes") or d.get("total_bytes_estimate")

    percent: float | None = None
    if total and total > 0:
        percent = downloaded / total * 100

    return ClipProgress(
        clip_index=index,
        phase=ClipPhase.DOWNLOADING,
        percent=percent,
        downloaded_bytes=downloaded if downloaded else None,
        total_bytes=total,
        speed=d.get("speed"),
        eta=d.get("eta"),
    )


class ClipService:
    """複数範囲の切り出しオーケストレーション

    各区間をyt-dlpのdownload_sectionで個別にダウンロード・切り出しする。
    """

    def __init__(
        self,
        ytdlp_client: object,
        *,
        ffmpeg_client: _FfmpegClient | None = None,
        max_workers: int = 4,
    ) -> None:
        self._ytdlp = ytdlp_client
        self._ffmpeg = ffmpeg_client
        self._max_workers = max_workers

    def execute(
        self,
        request: MultiClipRequest,
        on_progress: Callable[[ClipProgress], None] | None = None,
    ) -> MultiClipResult:
        """複数範囲の切り抜きリクエストを実行し、結果を返す。

        処理フロー:
        1. 各TimeRangeに対してdownload_sectionで範囲DL・切り出し
        2. AuthenticationRequiredErrorは即座にエスカレーション
        3. 個別失敗はエラー記録して続行
        4. MultiClipResult返却（入力順序を保持）
        """
        output_dir = Path(request.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        progress_lock = threading.Lock()

        def _notify(progress: ClipProgress) -> None:
            if on_progress:
                with progress_lock:
                    on_progress(progress)

        total = len(request.ranges)

        def _process_one(index: int) -> ClipOutcome:
            time_range = request.ranges[index]
            if request.filenames:
                filename = request.filenames[index]
            else:
                filename = build_numbered_filename(
                    request.filename, index + 1, total
                )
            filename = prepend_datetime_prefix(
                filename, request.broadcast_start_at
            )
            output_path = output_dir / filename

            def _ytdlp_hook(d: dict) -> None:
                p = _convert_ytdlp_progress(index, d)
                if p is not None:
                    _notify(p)

            margin = request.margin_seconds
            effective_start = max(0.0, time_range.start_seconds - margin)
            effective_end = time_range.end_seconds + margin

            try:
                _notify(
                    ClipProgress(clip_index=index, phase=ClipPhase.DOWNLOADING)
                )
                self._ytdlp.download_section(
                    request.video_id,
                    effective_start,
                    effective_end,
                    output_path,
                    cookie_file=request.cookie_file,
                    on_progress=_ytdlp_hook if on_progress else None,
                )

                if self._ffmpeg:
                    _notify(ClipProgress(clip_index=index, phase=ClipPhase.REENCODING))
                    self._ffmpeg.reencode(output_path)

                _notify(ClipProgress(clip_index=index, phase=ClipPhase.DONE))
            except Exception:
                try:
                    _notify(ClipProgress(clip_index=index, phase=ClipPhase.ERROR))
                except Exception:
                    pass
                raise

            return ClipOutcome(
                range=time_range,
                output_path=output_path,
            )

        # Single clip: no thread pool overhead
        if total <= 1:
            outcomes: list[ClipOutcome] = []
            for idx in range(total):
                try:
                    outcomes.append(_process_one(idx))
                except AuthenticationRequiredError:
                    raise
                except Exception as e:
                    outcomes.append(
                        ClipOutcome(
                            range=request.ranges[idx],
                            output_path=None,
                            error=str(e),
                        )
                    )
            return MultiClipResult(video_id=request.video_id, outcomes=outcomes)

        # Multiple clips: parallel execution
        workers = min(self._max_workers, total)
        outcomes_map: dict[int, ClipOutcome] = {}

        executor = ThreadPoolExecutor(max_workers=workers)
        try:
            future_to_idx = {
                executor.submit(_process_one, idx): idx for idx in range(total)
            }
            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    outcomes_map[idx] = future.result()
                except AuthenticationRequiredError:
                    # Cancel remaining futures and re-raise
                    for f in future_to_idx:
                        f.cancel()
                    raise
                except Exception as e:
                    outcomes_map[idx] = ClipOutcome(
                        range=request.ranges[idx],
                        output_path=None,
                        error=str(e),
                    )
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

        # Preserve input order
        outcomes = [outcomes_map[idx] for idx in range(total)]
        return MultiClipResult(video_id=request.video_id, outcomes=outcomes)
