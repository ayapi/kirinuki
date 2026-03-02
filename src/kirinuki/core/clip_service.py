"""切り抜きオーケストレーションサービス"""

import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from kirinuki.models.clip import ClipRequest, ClipResult


class FfmpegClient(Protocol):
    def check_available(self) -> None: ...

    def clip(
        self,
        input_path: Path,
        output_path: Path,
        start_seconds: float,
        end_seconds: float,
    ) -> None: ...


class ClipService:
    """動画DL→ffmpeg切り出し→一時ファイルクリーンアップのオーケストレーション"""

    def __init__(
        self,
        ytdlp_client: object,
        ffmpeg_client: FfmpegClient,
    ) -> None:
        self._ytdlp = ytdlp_client
        self._ffmpeg = ffmpeg_client

    def execute(
        self,
        request: ClipRequest,
        on_progress: Callable[[str], None] | None = None,
    ) -> ClipResult:
        """切り抜きリクエストを実行し、結果を返す。

        処理フロー:
        1. ffmpeg存在確認
        2. 出力先親ディレクトリ存在確認
        3. 一時ディレクトリに動画DL
        4. ffmpegで指定区間切り出し
        5. ClipResult返却
        """
        self._ffmpeg.check_available()

        output_path = request.output_path
        assert output_path is not None

        if not output_path.parent.exists():
            raise FileNotFoundError(
                f"出力先ディレクトリが存在しません: {output_path.parent}"
            )

        def _notify(msg: str) -> None:
            if on_progress:
                on_progress(msg)

        with tempfile.TemporaryDirectory() as tmpdir:
            _notify("ダウンロード中...")
            downloaded_path: Path = self._ytdlp.download_video(
                request.url,
                Path(tmpdir),
                cookie_file=request.cookie_file,
            )

            _notify("切り出し中...")
            assert request.start_seconds is not None
            assert request.end_seconds is not None
            self._ffmpeg.clip(
                downloaded_path,
                output_path,
                request.start_seconds,
                request.end_seconds,
            )

        return ClipResult(
            output_path=output_path,
            video_id=request.url,
            start_seconds=request.start_seconds,
            end_seconds=request.end_seconds,
            duration_seconds=request.end_seconds - request.start_seconds,
        )
