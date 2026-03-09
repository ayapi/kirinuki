"""切り抜きリクエスト・結果のデータモデル"""

from pathlib import Path

from pydantic import BaseModel, model_validator

SUPPORTED_FORMATS = {"mp4", "mkv", "webm"}


class ClipRequest(BaseModel):
    url: str
    start_seconds: float | None = None
    end_seconds: float | None = None
    output_path: Path | None = None
    output_format: str = "mp4"
    cookie_file: Path | None = None
    temp_dir: Path | None = None

    @model_validator(mode="after")
    def validate_time_range(self) -> "ClipRequest":
        if self.start_seconds is None and self.end_seconds is None:
            raise ValueError("start_secondsとend_secondsの少なくとも一方を指定してください")
        if self.start_seconds is not None and self.start_seconds < 0:
            raise ValueError("start_secondsは0以上である必要があります")
        if (
            self.start_seconds is not None
            and self.end_seconds is not None
            and self.start_seconds >= self.end_seconds
        ):
            raise ValueError("start_secondsはend_secondsより小さい必要があります")
        if self.output_format not in SUPPORTED_FORMATS:
            raise ValueError(
                f"サポートされていないフォーマットです: {self.output_format}"
                f" (サポート対象: {', '.join(sorted(SUPPORTED_FORMATS))})"
            )
        return self


class ClipResult(BaseModel):
    output_path: Path
    video_id: str
    start_seconds: float
    end_seconds: float
    duration_seconds: float


# --- Multi-clip models ---


class TimeRange(BaseModel):
    start_seconds: float
    end_seconds: float

    @model_validator(mode="after")
    def validate_range(self) -> "TimeRange":
        if self.start_seconds < 0:
            raise ValueError("start_secondsは0以上である必要があります")
        if self.start_seconds >= self.end_seconds:
            raise ValueError("start_secondsはend_secondsより小さい必要があります")
        return self


class MultiClipRequest(BaseModel):
    video_id: str
    filename: str
    output_dir: Path
    ranges: list[TimeRange]
    cookie_file: Path | None = None

    @model_validator(mode="after")
    def validate_ranges(self) -> "MultiClipRequest":
        if len(self.ranges) < 1:
            raise ValueError("rangesは1つ以上指定してください")
        # 拡張子がなければ .mp4 を付与
        from pathlib import PurePosixPath

        if not PurePosixPath(self.filename).suffix:
            self.filename = f"{self.filename}.mp4"
        return self


class ClipOutcome(BaseModel):
    """個別の切り出し結果"""

    range: TimeRange
    output_path: Path | None
    error: str | None = None


class MultiClipResult(BaseModel):
    video_id: str
    outcomes: list[ClipOutcome]

    @property
    def success_count(self) -> int:
        return sum(1 for o in self.outcomes if o.output_path is not None)

    @property
    def failure_count(self) -> int:
        return sum(1 for o in self.outcomes if o.output_path is None)
