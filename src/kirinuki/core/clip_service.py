"""切り抜きオーケストレーションサービス"""

import logging
from collections.abc import Callable
from pathlib import Path

from kirinuki.core.clip_utils import build_numbered_filename
from kirinuki.core.errors import AuthenticationRequiredError
from kirinuki.models.clip import (
    ClipOutcome,
    MultiClipRequest,
    MultiClipResult,
)

logger = logging.getLogger(__name__)


class ClipService:
    """複数範囲の切り出しオーケストレーション

    各区間をyt-dlpのdownload_sectionで個別にダウンロード・切り出しする。
    """

    def __init__(
        self,
        ytdlp_client: object,
    ) -> None:
        self._ytdlp = ytdlp_client

    def execute(
        self,
        request: MultiClipRequest,
        on_progress: Callable[[str], None] | None = None,
    ) -> MultiClipResult:
        """複数範囲の切り抜きリクエストを実行し、結果を返す。

        処理フロー:
        1. 各TimeRangeに対してdownload_sectionで範囲DL・切り出し
        2. 個別失敗はエラー記録して続行
        3. MultiClipResult返却
        """
        output_dir = Path(request.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        def _notify(msg: str) -> None:
            if on_progress:
                on_progress(msg)

        total = len(request.ranges)
        outcomes: list[ClipOutcome] = []

        for i, time_range in enumerate(request.ranges, 1):
            if request.filenames:
                filename = request.filenames[i - 1]
            else:
                filename = build_numbered_filename(request.filename, i, total)
            output_path = output_dir / filename

            _notify(f"[{i}/{total}] ダウンロード・切り抜き中...")

            try:
                self._ytdlp.download_section(
                    request.video_id,
                    time_range.start_seconds,
                    time_range.end_seconds,
                    output_path,
                    cookie_file=request.cookie_file,
                )
                outcomes.append(
                    ClipOutcome(
                        range=time_range,
                        output_path=output_path,
                    )
                )
            except AuthenticationRequiredError:
                raise
            except Exception as e:
                outcomes.append(
                    ClipOutcome(
                        range=time_range,
                        output_path=None,
                        error=str(e),
                    )
                )

        return MultiClipResult(
            video_id=request.video_id,
            outcomes=outcomes,
        )
