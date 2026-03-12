"""切り抜き推薦関連のデータモデル"""

from dataclasses import dataclass, field
from datetime import datetime

from pydantic import BaseModel, Field


class SegmentRecommendation(BaseModel):
    """切り抜き推薦結果。LLM評価の出力をそのままマッピング。"""

    segment_id: int
    video_id: str
    start_time: float = Field(description="区間開始時刻（秒）")
    end_time: float = Field(description="区間終了時刻（秒）")
    score: int = Field(ge=1, le=10, description="切り抜き推薦スコア")
    summary: str = Field(description="話題の要約（1〜2文）")
    appeal: str = Field(description="切り抜きの魅力紹介")
    prompt_version: str = Field(description="評価に使用したプロンプトバージョン")


@dataclass
class SuggestOptions:
    channel_id: str | None = None
    count: int = 3
    threshold: int = 7
    video_ids: list[str] | None = None
    until: datetime | None = None


@dataclass
class VideoWithRecommendations:
    video_id: str
    title: str
    published_at: str
    recommendations: list[SegmentRecommendation] = field(default_factory=list)


@dataclass
class SuggestResult:
    videos: list[VideoWithRecommendations]
    total_candidates: int
    filtered_count: int
    warnings: list[str] = field(default_factory=list)
