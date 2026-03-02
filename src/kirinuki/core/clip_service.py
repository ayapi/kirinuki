"""切り抜きオーケストレーションサービス"""

from collections.abc import Callable
from pathlib import Path

from kirinuki.core.clip_utils import build_numbered_filename
from kirinuki.models.clip import (
    ClipOutcome,
    MultiClipRequest,
    MultiClipResult,
)


class ClipService:
    """複数範囲の切り出しオーケストレーション"""

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
        1. 出力先ディレクトリを作成（存在しない場合）
        2. 各TimeRangeに対してdownload_sectionを呼び出し
        3. 個別失敗はエラー記録して続行
        4. MultiClipResult返却
        """
        output_dir = Path(request.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        def _notify(msg: str) -> None:
            if on_progress:
                on_progress(msg)

        total = len(request.ranges)
        outcomes: list[ClipOutcome] = []

        for i, time_range in enumerate(request.ranges, 1):
            filename = build_numbered_filename(request.filename, i, total)
            output_path = output_dir / filename

            _notify(f"[{i}/{total}] 切り抜き中...")

            try:
                result_path = self._ytdlp.download_section(
                    request.video_id,
                    time_range.start_seconds,
                    time_range.end_seconds,
                    output_path=output_path,
                    cookie_file=request.cookie_file,
                )
                outcomes.append(
                    ClipOutcome(
                        range=time_range,
                        output_path=result_path,
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
