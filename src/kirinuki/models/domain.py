"""ドメインモデル定義"""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel


class MatchType(str, Enum):
    KEYWORD = "keyword"
    SEMANTIC = "semantic"
    HYBRID = "hybrid"


class SkipReason(str, Enum):
    NO_SUBTITLE_AVAILABLE = "no_subtitle_available"
    NO_TARGET_LANGUAGE = "no_target_language"
    PARSE_FAILED = "parse_failed"
    FETCH_FAILED = "fetch_failed"
    NOT_LIVE_ARCHIVE = "not_live_archive"


class Channel(BaseModel):
    channel_id: str
    name: str
    url: str
    last_synced_at: datetime | None = None


class ChannelSummary(BaseModel):
    channel_id: str
    name: str
    url: str
    video_count: int
    last_synced_at: datetime | None = None


class Video(BaseModel):
    video_id: str
    channel_id: str
    title: str
    published_at: datetime | None = None
    duration_seconds: int
    subtitle_language: str
    is_auto_subtitle: bool
    synced_at: datetime | None = None


class VideoSummary(BaseModel):
    video_id: str
    title: str
    published_at: datetime | None = None
    duration_seconds: int


class SubtitleEntry(BaseModel):
    """yt-dlpから取得した字幕エントリ（DB保存前）"""

    start_ms: int
    duration_ms: int
    text: str


class SubtitleLine(BaseModel):
    """DB保存済みの字幕行"""

    id: int
    video_id: str
    start_ms: int
    duration_ms: int
    text: str


class Segment(BaseModel):
    id: int
    video_id: str
    start_ms: int
    end_ms: int
    summary: str


class TopicSegment(BaseModel):
    """LLMから返される話題セグメント（DB保存前）"""

    start_ms: int
    end_ms: int
    summary: str


class SearchResult(BaseModel):
    video_title: str
    channel_name: str
    start_time_ms: int
    end_time_ms: int
    summary: str
    youtube_url: str
    score: float = 0.0
    match_type: MatchType | None = None
    snippet: str | None = None
    similarity: float | None = None


class SyncError(BaseModel):
    video_id: str
    reason: str


class SyncResult(BaseModel):
    already_synced: int = 0
    newly_synced: int = 0
    skipped: int = 0
    auth_errors: int = 0
    unavailable_skipped: int = 0
    not_live_skipped: int = 0
    segmentation_retried: int = 0
    segmentation_retry_failed: int = 0
    errors: list[SyncError] = []
    skip_reasons: dict[str, int] = {}
