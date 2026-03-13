"""推薦結果フォーマッター"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from kirinuki.core.clip_utils import build_youtube_url
from kirinuki.models.recommendation import SuggestResult, VideoWithRecommendations


def format_broadcast_date(iso_str: str) -> str:
    """ISO 8601文字列をローカルタイムゾーンの 'YYYY-MM-DD HH:MM' に変換する。"""
    try:
        dt = datetime.fromisoformat(iso_str)
        return dt.astimezone().strftime("%Y-%m-%d %H:%M")
    except (ValueError, TypeError):
        return iso_str


def format_time(seconds: float) -> str:
    """秒数を H:MM:SS または M:SS 形式にフォーマットする"""
    total = int(seconds)
    h, remainder = divmod(total, 3600)
    m, s = divmod(remainder, 60)
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def format_time_range(start_seconds: float, end_seconds: float) -> str:
    """2つの秒数を 'MM:SS-MM:SS' 形式の文字列に変換する。

    1時間以上の場合は 'H:MM:SS-H:MM:SS' 形式。
    clipコマンドのtime_ranges引数にそのまま渡せる形式を返す。
    """
    return f"{format_time(start_seconds)}-{format_time(end_seconds)}"


class RecommendationFormatter:
    def format_text(self, result: SuggestResult) -> str:
        """推薦結果を人間可読テキストにフォーマットする。"""
        if not result.videos:
            return (
                f"推薦候補: 0件（全{result.total_candidates}件中、該当なし）\n"
                "閾値を下げて再実行してください（例: --threshold 5）"
            )

        # 動画グループを最高スコアの降順でソート
        sorted_videos = sorted(
            result.videos,
            key=lambda v: max(r.score for r in v.recommendations),
            reverse=True,
        )

        lines: list[str] = []
        lines.append(f"推薦候補: {result.filtered_count}件（全{result.total_candidates}件中）")
        lines.append("")

        for video in sorted_videos:
            lines.append(f"## {video.title}")
            lines.append(f"   配信日時: {format_broadcast_date(video.broadcast_start_at)}")
            lines.append("")

            # 動画内は時系列順
            sorted_recs = sorted(video.recommendations, key=lambda r: r.start_time)
            for rec in sorted_recs:
                time_range = format_time_range(rec.start_time, rec.end_time)
                url = build_youtube_url(rec.video_id, int(rec.start_time * 1000))
                lines.append(f"  [{rec.score}/10] {time_range}")
                lines.append(f"    要約: {rec.summary}")
                lines.append(f"    魅力: {rec.appeal}")
                lines.append(f"    URL: {url}")
                lines.append("")

        return "\n".join(lines)

    def format_json(self, result: SuggestResult) -> str:
        """推薦結果をJSON文字列にフォーマットする。"""
        data = self._to_dict(result)
        return json.dumps(data, ensure_ascii=False, indent=2)

    def _to_dict(self, result: SuggestResult) -> dict[str, Any]:
        return {
            "total_candidates": result.total_candidates,
            "filtered_count": result.filtered_count,
            "videos": [self._video_to_dict(v) for v in result.videos],
        }

    def _video_to_dict(self, video: VideoWithRecommendations) -> dict[str, Any]:
        return {
            "video_id": video.video_id,
            "title": video.title,
            "broadcast_start_at": format_broadcast_date(video.broadcast_start_at),
            "recommendations": [
                {
                    "segment_id": r.segment_id,
                    "start_time": r.start_time,
                    "end_time": r.end_time,
                    "score": r.score,
                    "summary": r.summary,
                    "appeal": r.appeal,
                    "youtube_url": build_youtube_url(r.video_id, int(r.start_time * 1000)),
                }
                for r in video.recommendations
            ],
        }
