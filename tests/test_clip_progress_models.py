"""ClipPhase / ClipProgress データモデルのテスト"""

from kirinuki.models.clip import ClipPhase, ClipProgress


class TestClipPhase:
    def test_enum_values(self) -> None:
        assert ClipPhase.DOWNLOADING.value == "downloading"
        assert ClipPhase.REENCODING.value == "reencoding"
        assert ClipPhase.DONE.value == "done"
        assert ClipPhase.ERROR.value == "error"

    def test_all_phases_defined(self) -> None:
        assert len(ClipPhase) == 4


class TestClipProgress:
    def test_minimal_construction(self) -> None:
        p = ClipProgress(clip_index=0, phase=ClipPhase.DOWNLOADING)
        assert p.clip_index == 0
        assert p.phase == ClipPhase.DOWNLOADING
        assert p.percent is None
        assert p.downloaded_bytes is None
        assert p.total_bytes is None
        assert p.speed is None
        assert p.eta is None

    def test_full_construction(self) -> None:
        p = ClipProgress(
            clip_index=2,
            phase=ClipPhase.DOWNLOADING,
            percent=45.2,
            downloaded_bytes=12_300_000,
            total_bytes=27_200_000,
            speed=5_200_000.0,
            eta=3,
        )
        assert p.clip_index == 2
        assert p.percent == 45.2
        assert p.downloaded_bytes == 12_300_000
        assert p.total_bytes == 27_200_000
        assert p.speed == 5_200_000.0
        assert p.eta == 3

    def test_frozen_immutable(self) -> None:
        p = ClipProgress(clip_index=0, phase=ClipPhase.DONE)
        try:
            p.clip_index = 1  # type: ignore[misc]
            assert False, "Should raise"
        except AttributeError:
            pass

    def test_reencoding_phase(self) -> None:
        p = ClipProgress(clip_index=1, phase=ClipPhase.REENCODING)
        assert p.phase == ClipPhase.REENCODING

    def test_error_phase(self) -> None:
        p = ClipProgress(clip_index=0, phase=ClipPhase.ERROR)
        assert p.phase == ClipPhase.ERROR
