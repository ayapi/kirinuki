"""切り抜き動画生成のオーケストレーションサービス"""

import logging
import tempfile
from pathlib import Path
from typing import Protocol

from kirinuki.core.clip_utils import extract_video_id, format_default_filename
from kirinuki.core.errors import TimeRangeError
from kirinuki.models.clip import ClipRequest, ClipResult

logger = logging.getLogger(__name__)


class _YtdlpClient(Protocol):
    def fetch_video_metadata(self, video_id: str) -> object: ...

    def download_video(
        self,
        video_id: str,
        output_dir: Path,
        cookie_file: Path | None = None,
    ) -> Path: ...


class _FfmpegClient(Protocol):
    def check_available(self) -> None: ...

    def clip(
        self,
        input_path: Path,
        output_path: Path,
        start_seconds: float,
        end_seconds: float,
    ) -> None: ...


class SegmentExtractorServiceImpl:
    """DL → 区間切り出し → クリーンアップのオーケストレーション"""

    def __init__(
        self,
        ytdlp_client: _YtdlpClient,
        ffmpeg_client: _FfmpegClient,
    ) -> None:
        self._ytdlp = ytdlp_client
        self._ffmpeg = ffmpeg_client

    def extract(self, request: ClipRequest) -> ClipResult:
        """指定URLの指定区間を切り出した動画を生成する。"""
        # 1. ffmpeg存在確認
        self._ffmpeg.check_available()

        # 2. URL解析
        video_id = extract_video_id(request.url)

        # 3. メタデータ取得・時間範囲検証
        meta = self._ytdlp.fetch_video_metadata(video_id)
        duration = meta.duration_seconds  # type: ignore[attr-defined]

        start = request.start_seconds if request.start_seconds is not None else 0.0
        end = request.end_seconds if request.end_seconds is not None else float(duration)

        if start >= duration:
            raise TimeRangeError(f"開始時刻({start}秒)が動画の長さ({duration}秒)を超えています")
        if end > duration:
            raise TimeRangeError(f"終了時刻({end}秒)が動画の長さ({duration}秒)を超えています")

        # 4. 出力パス決定
        output_path = request.output_path
        if output_path is None:
            filename = format_default_filename(video_id, start, end, request.output_format)
            output_path = Path.cwd() / filename

        # 5. 一時ディレクトリで DL → 切り出し → クリーンアップ
        if request.temp_dir is not None:
            request.temp_dir.mkdir(parents=True, exist_ok=True)
            self._run_pipeline(video_id, request, start, end, output_path, request.temp_dir)
        else:
            with tempfile.TemporaryDirectory() as td:
                temp_dir = Path(td)
                self._run_pipeline(video_id, request, start, end, output_path, temp_dir)

        return ClipResult(
            output_path=output_path,
            video_id=video_id,
            start_seconds=start,
            end_seconds=end,
            duration_seconds=end - start,
        )

    def _run_pipeline(
        self,
        video_id: str,
        request: ClipRequest,
        start: float,
        end: float,
        output_path: Path,
        temp_dir: Path,
    ) -> None:
        """DL → 切り出しパイプラインを実行する。"""
        downloaded_path = self._ytdlp.download_video(
            video_id,
            temp_dir,
            cookie_file=request.cookie_file,
        )

        try:
            self._ffmpeg.clip(downloaded_path, output_path, start, end)
        finally:
            # ダウンロードした元動画を削除
            if downloaded_path.exists():
                downloaded_path.unlink()
                logger.debug("一時ファイル削除: %s", downloaded_path)
