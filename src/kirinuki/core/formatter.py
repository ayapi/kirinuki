"""推薦結果フォーマッター"""

from __future__ import annotations

import json
from typing import Any

from kirinuki.models.recommendation import SuggestResult, VideoWithRecommendations


def _format_time(seconds: float) -> str:
    """秒数を H:MM:SS または M:SS 形式にフォーマットする"""
    total = int(seconds)
    h, remainder = divmod(total, 3600)
    m, s = divmod(remainder, 60)
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


class RecommendationFormatter:
    @staticmethod
    def build_youtube_url(video_id: str, start_seconds: int) -> str:
        """タイムスタンプ付きYouTube URLを生成する。"""
        return f"https://www.youtube.com/watch?v={video_id}&t={start_seconds}"

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
            lines.append(f"   配信日時: {video.published_at}")
            lines.append("")

            # 動画内は時系列順
            sorted_recs = sorted(video.recommendations, key=lambda r: r.start_time)
            for rec in sorted_recs:
                start_str = _format_time(rec.start_time)
                end_str = _format_time(rec.end_time)
                url = self.build_youtube_url(rec.video_id, int(rec.start_time))
                lines.append(f"  [{rec.score}/10] {start_str} 〜 {end_str}")
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
            "published_at": video.published_at,
            "recommendations": [
                {
                    "segment_id": r.segment_id,
                    "start_time": r.start_time,
                    "end_time": r.end_time,
                    "score": r.score,
                    "summary": r.summary,
                    "appeal": r.appeal,
                    "youtube_url": self.build_youtube_url(r.video_id, int(r.start_time)),
                }
                for r in video.recommendations
            ],
        }
