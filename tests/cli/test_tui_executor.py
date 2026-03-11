"""TUIクリップ実行機能のユニットテスト"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from kirinuki.cli.tui import execute_clips
from kirinuki.models.clip import ClipOutcome, MultiClipResult, TimeRange
from kirinuki.models.tui import ClipCandidate


def _make_candidate(
    video_id: str = "dQw4w9WgXcQ",
    start_ms: int = 60000,
    end_ms: int = 120000,
    summary: str = "テスト話題",
) -> ClipCandidate:
    return ClipCandidate(
        video_id=video_id,
        start_ms=start_ms,
        end_ms=end_ms,
        summary=summary,
        display_label=f"{start_ms}-{end_ms} {summary}",
    )


class TestExecuteClips:
    def test_empty_selection_returns_empty(self) -> None:
        mock_service = MagicMock()
        outcomes = execute_clips([], mock_service, Path("/tmp/out"))
        assert outcomes == []
        mock_service.execute.assert_not_called()

    def test_single_clip_success(self) -> None:
        candidate = _make_candidate()
        mock_service = MagicMock()
        mock_service.execute.return_value = MultiClipResult(
            video_id="dQw4w9WgXcQ",
            outcomes=[
                ClipOutcome(
                    range=TimeRange(start_seconds=60.0, end_seconds=120.0),
                    output_path=Path("/tmp/out/dQw4w9WgXcQ-1m00s-テスト話題.mp4"),
                )
            ],
        )

        outcomes = execute_clips([candidate], mock_service, Path("/tmp/out"))
        assert len(outcomes) == 1
        assert outcomes[0].output_path is not None
        mock_service.execute.assert_called_once()

    def test_multiple_clips_same_video_grouped(self) -> None:
        """同じ動画IDの候補はグルーピングされ、executeは1回だけ呼ばれる"""
        candidates = [
            _make_candidate(summary="成功する話題"),
            _make_candidate(start_ms=180000, end_ms=240000, summary="失敗する話題"),
        ]
        mock_service = MagicMock()
        mock_service.execute.return_value = MultiClipResult(
            video_id="dQw4w9WgXcQ",
            outcomes=[
                ClipOutcome(
                    range=TimeRange(start_seconds=60.0, end_seconds=120.0),
                    output_path=Path("/tmp/success.mp4"),
                ),
                ClipOutcome(
                    range=TimeRange(start_seconds=180.0, end_seconds=240.0),
                    output_path=None,
                    error="ffmpeg error",
                ),
            ],
        )

        outcomes = execute_clips(candidates, mock_service, Path("/tmp/out"))
        assert len(outcomes) == 2
        assert outcomes[0].output_path is not None
        assert outcomes[1].error == "ffmpeg error"
        # 同じ動画IDなのでexecuteは1回だけ
        mock_service.execute.assert_called_once()

    def test_different_videos_separate_requests(self) -> None:
        """異なる動画IDの候補は別々のリクエストになる"""
        candidates = [
            _make_candidate(video_id="dQw4w9WgXcQ", summary="動画A"),
            _make_candidate(video_id="abc12345678", summary="動画B"),
        ]
        mock_service = MagicMock()
        mock_service.execute.side_effect = [
            MultiClipResult(
                video_id="dQw4w9WgXcQ",
                outcomes=[
                    ClipOutcome(
                        range=TimeRange(start_seconds=60.0, end_seconds=120.0),
                        output_path=Path("/tmp/a.mp4"),
                    )
                ],
            ),
            MultiClipResult(
                video_id="abc12345678",
                outcomes=[
                    ClipOutcome(
                        range=TimeRange(start_seconds=60.0, end_seconds=120.0),
                        output_path=Path("/tmp/b.mp4"),
                    )
                ],
            ),
        ]

        outcomes = execute_clips(candidates, mock_service, Path("/tmp/out"))
        assert len(outcomes) == 2
        # 異なる動画IDなのでexecuteは2回
        assert mock_service.execute.call_count == 2

    def test_progress_callback(self) -> None:
        candidate = _make_candidate()
        mock_service = MagicMock()
        mock_service.execute.return_value = MultiClipResult(
            video_id="dQw4w9WgXcQ",
            outcomes=[
                ClipOutcome(
                    range=TimeRange(start_seconds=60.0, end_seconds=120.0),
                    output_path=Path("/tmp/out.mp4"),
                )
            ],
        )
        progress_messages: list[str] = []

        execute_clips(
            [candidate], mock_service, Path("/tmp/out"),
            on_progress=progress_messages.append,
        )
        assert len(progress_messages) == 1
        assert "[1/1]" in progress_messages[0]
        assert "切り抜き中" in progress_messages[0]

    def test_service_exception_recorded_as_error(self) -> None:
        candidate = _make_candidate()
        mock_service = MagicMock()
        mock_service.execute.side_effect = RuntimeError("network error")

        outcomes = execute_clips([candidate], mock_service, Path("/tmp/out"))
        assert len(outcomes) == 1
        assert outcomes[0].error == "network error"
        assert outcomes[0].output_path is None

    def test_filename_uses_generate_clip_filename(self) -> None:
        candidate = _make_candidate(start_ms=1083000, end_ms=1200000, summary="面白い話題")
        mock_service = MagicMock()
        mock_service.execute.return_value = MultiClipResult(
            video_id="dQw4w9WgXcQ",
            outcomes=[
                ClipOutcome(
                    range=TimeRange(start_seconds=1083.0, end_seconds=1200.0),
                    output_path=Path("/tmp/out.mp4"),
                )
            ],
        )

        execute_clips([candidate], mock_service, Path("/tmp/out"))
        call_args = mock_service.execute.call_args
        request = call_args[0][0]
        assert request.filenames == ["dQw4w9WgXcQ-18m03s-面白い話題.mp4"]
