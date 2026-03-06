"""切り抜きオーケストレーションサービス"""

import logging
import tempfile
from collections.abc import Callable
from pathlib import Path

from kirinuki.core.clip_utils import build_numbered_filename
from kirinuki.models.clip import (
    ClipOutcome,
    MultiClipRequest,
    MultiClipResult,
)

logger = logging.getLogger(__name__)


class ClipService:
    """複数範囲の切り出しオーケストレーション

    動画を1回だけダウンロードし、各区間をffmpegで切り出す。
    """

    def __init__(
        self,
        ytdlp_client: object,
        ffmpeg_client: object,
    ) -> None:
        self._ytdlp = ytdlp_client
        self._ffmpeg = ffmpeg_client

    def execute(
        self,
        request: MultiClipRequest,
        on_progress: Callable[[str], None] | None = None,
    ) -> MultiClipResult:
        """複数範囲の切り抜きリクエストを実行し、結果を返す。

        処理フロー:
        1. 動画を一時ディレクトリに1回だけダウンロード
        2. 各TimeRangeに対してffmpegで区間切り出し
        3. 個別失敗はエラー記録して続行
        4. 一時ファイルをクリーンアップ
        5. MultiClipResult返却
        """
        output_dir = Path(request.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        def _notify(msg: str) -> None:
            if on_progress:
                on_progress(msg)

        with tempfile.TemporaryDirectory() as td:
            temp_dir = Path(td)

            _notify("動画をダウンロード中...")
            downloaded_path = self._ytdlp.download_video(
                request.video_id,
                temp_dir,
                cookie_file=request.cookie_file,
            )

            total = len(request.ranges)
            outcomes: list[ClipOutcome] = []

            for i, time_range in enumerate(request.ranges, 1):
                filename = build_numbered_filename(request.filename, i, total)
                output_path = output_dir / filename

                _notify(f"[{i}/{total}] 切り抜き中...")

                try:
                    self._ffmpeg.clip(
                        downloaded_path,
                        output_path,
                        time_range.start_seconds,
                        time_range.end_seconds,
                    )
                    outcomes.append(
                        ClipOutcome(
                            range=time_range,
                            output_path=output_path,
                        )
                    )
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
