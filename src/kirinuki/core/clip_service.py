"""切り抜きオーケストレーションサービス"""

import logging
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Protocol

from kirinuki.core.clip_utils import build_numbered_filename
from kirinuki.core.errors import AuthenticationRequiredError
from kirinuki.models.clip import (
    ClipOutcome,
    MultiClipRequest,
    MultiClipResult,
)

logger = logging.getLogger(__name__)


class _FfmpegClient(Protocol):
    def reencode(self, file_path: Path) -> None: ...


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
        on_progress: Callable[[str], None] | None = None,
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

        def _notify(msg: str) -> None:
            if on_progress:
                with progress_lock:
                    on_progress(msg)

        total = len(request.ranges)

        def _process_one(index: int) -> ClipOutcome:
            i = index + 1
            time_range = request.ranges[index]
            if request.filenames:
                filename = request.filenames[index]
            else:
                filename = build_numbered_filename(request.filename, i, total)
            output_path = output_dir / filename

            _notify(f"[{i}/{total}] ダウンロード・切り抜き中...")

            self._ytdlp.download_section(
                request.video_id,
                time_range.start_seconds,
                time_range.end_seconds,
                output_path,
                cookie_file=request.cookie_file,
            )
            if self._ffmpeg:
                self._ffmpeg.reencode(output_path)
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
