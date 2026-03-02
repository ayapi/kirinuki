"""TUI表示・インタラクティブ選択用のデータモデル"""

from pydantic import BaseModel


class ClipCandidate(BaseModel):
    """TUI表示・切り抜き実行用の統一データモデル。

    search/segments/suggestの各結果型をこのモデルに変換し、
    TUIメニューでの表示と切り抜き実行に必要な情報を統一的に保持する。
    """

    video_id: str
    start_ms: int
    end_ms: int
    summary: str
    display_label: str

    # searchコマンド用（オプション）
    video_title: str | None = None
    channel_name: str | None = None
    score: float | None = None
    match_type: str | None = None

    # suggestコマンド用（オプション）
    recommend_score: int | None = None
    appeal: str | None = None
