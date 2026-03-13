"""ProgressRenderer のユニットテスト"""

import io

from kirinuki.cli.progress_renderer import ProgressRenderer
from kirinuki.models.clip import ClipPhase, ClipProgress


class TestFormatProgressLine:
    """進捗行フォーマットのテスト"""

    def test_downloading_full_info(self) -> None:
        """ダウンロード中: 全情報あり"""
        r = ProgressRenderer(total=1, output=io.StringIO())
        p = ClipProgress(
            clip_index=0,
            phase=ClipPhase.DOWNLOADING,
            percent=45.2,
            downloaded_bytes=12_300_000,
            total_bytes=27_200_000,
            speed=5_200_000.0,
            eta=3,
        )
        line = r._format_line(p)
        assert "ダウンロード中" in line
        assert "45.2%" in line
        assert "12.3MB" in line
        assert "27.2MB" in line
        assert "5.2MB/s" in line
        assert "0:03" in line

    def test_downloading_minimal_info(self) -> None:
        """ダウンロード中: 一部情報欠損"""
        r = ProgressRenderer(total=1, output=io.StringIO())
        p = ClipProgress(
            clip_index=0,
            phase=ClipPhase.DOWNLOADING,
            percent=10.0,
        )
        line = r._format_line(p)
        assert "ダウンロード中" in line
        assert "10.0%" in line
        # No size/speed/eta info
        assert "MB/s" not in line

    def test_downloading_no_percent(self) -> None:
        """ダウンロード中: パーセントなし"""
        r = ProgressRenderer(total=1, output=io.StringIO())
        p = ClipProgress(
            clip_index=0,
            phase=ClipPhase.DOWNLOADING,
            downloaded_bytes=5_000_000,
        )
        line = r._format_line(p)
        assert "ダウンロード中" in line
        assert "5.0MB" in line

    def test_reencoding(self) -> None:
        """再エンコード中"""
        r = ProgressRenderer(total=1, output=io.StringIO())
        p = ClipProgress(clip_index=0, phase=ClipPhase.REENCODING)
        line = r._format_line(p)
        assert "再エンコード中" in line

    def test_done(self) -> None:
        """完了"""
        r = ProgressRenderer(total=1, output=io.StringIO())
        p = ClipProgress(clip_index=0, phase=ClipPhase.DONE)
        line = r._format_line(p)
        assert "完了" in line

    def test_error(self) -> None:
        """エラー"""
        r = ProgressRenderer(total=1, output=io.StringIO())
        p = ClipProgress(clip_index=0, phase=ClipPhase.ERROR)
        line = r._format_line(p)
        assert "エラー" in line

    def test_format_bytes_kb(self) -> None:
        """KB表示"""
        r = ProgressRenderer(total=1, output=io.StringIO())
        p = ClipProgress(
            clip_index=0,
            phase=ClipPhase.DOWNLOADING,
            downloaded_bytes=500_000,
            total_bytes=900_000,
        )
        line = r._format_line(p)
        assert "500.0KB" in line or "KB" in line

    def test_format_bytes_gb(self) -> None:
        """GB表示"""
        r = ProgressRenderer(total=1, output=io.StringIO())
        p = ClipProgress(
            clip_index=0,
            phase=ClipPhase.DOWNLOADING,
            downloaded_bytes=1_500_000_000,
            total_bytes=2_000_000_000,
        )
        line = r._format_line(p)
        assert "1.5GB" in line

    def test_eta_minutes(self) -> None:
        """ETAが分:秒で表示される"""
        r = ProgressRenderer(total=1, output=io.StringIO())
        p = ClipProgress(
            clip_index=0,
            phase=ClipPhase.DOWNLOADING,
            percent=50.0,
            eta=125,  # 2:05
        )
        line = r._format_line(p)
        assert "2:05" in line


class TestSingleClipRendering:
    """単一クリップ描画のテスト"""

    def test_update_writes_to_output(self) -> None:
        """update呼び出しで出力に書き込まれる"""
        output = io.StringIO()
        r = ProgressRenderer(total=1, output=output)
        # Pretend it's a TTY
        r._is_tty = True
        p = ClipProgress(
            clip_index=0,
            phase=ClipPhase.DOWNLOADING,
            percent=30.0,
        )
        r.update(p)
        content = output.getvalue()
        assert "ダウンロード中" in content
        assert "30.0%" in content

    def test_non_tty_no_output(self) -> None:
        """非TTY環境では進捗描画しない"""
        output = io.StringIO()
        r = ProgressRenderer(total=1, output=output)
        r._is_tty = False
        p = ClipProgress(
            clip_index=0,
            phase=ClipPhase.DOWNLOADING,
            percent=30.0,
        )
        r.update(p)
        assert output.getvalue() == ""

    def test_finish_clears_lines(self) -> None:
        """finish()で進捗行がクリアされる"""
        output = io.StringIO()
        r = ProgressRenderer(total=1, output=output)
        r._is_tty = True
        p = ClipProgress(clip_index=0, phase=ClipPhase.DOWNLOADING, percent=50.0)
        r.update(p)
        r.finish()
        content = output.getvalue()
        # Should contain cursor up and clear line sequences at the end
        assert "\033[" in content


class TestMultiClipRendering:
    """マルチクリップ描画のテスト"""

    def test_multi_clip_header(self) -> None:
        """マルチクリップ: 全体進捗ヘッダーが表示される"""
        output = io.StringIO()
        r = ProgressRenderer(total=3, output=output)
        r._is_tty = True
        p = ClipProgress(clip_index=0, phase=ClipPhase.DOWNLOADING, percent=50.0)
        r.update(p)
        content = output.getvalue()
        assert "[0/3]" in content

    def test_multi_clip_completed_count_updates(self) -> None:
        """マルチクリップ: 完了数が更新される"""
        output = io.StringIO()
        r = ProgressRenderer(total=3, output=output)
        r._is_tty = True

        # Clip 0 downloading
        r.update(ClipProgress(clip_index=0, phase=ClipPhase.DOWNLOADING, percent=50.0))
        # Clip 1 downloading
        r.update(ClipProgress(clip_index=1, phase=ClipPhase.DOWNLOADING, percent=20.0))
        # Clip 0 done
        r.update(ClipProgress(clip_index=0, phase=ClipPhase.DONE))

        content = output.getvalue()
        assert "[1/3]" in content

    def test_multi_clip_individual_lines(self) -> None:
        """マルチクリップ: 処理中のクリップごとに行が表示される"""
        output = io.StringIO()
        r = ProgressRenderer(total=3, output=output)
        r._is_tty = True

        r.update(ClipProgress(clip_index=0, phase=ClipPhase.DOWNLOADING, percent=50.0))
        r.update(ClipProgress(clip_index=2, phase=ClipPhase.REENCODING))

        content = output.getvalue()
        assert "#1" in content  # clip_index 0 → display as #1
        assert "#3" in content  # clip_index 2 → display as #3

    def test_done_clips_removed_from_active(self) -> None:
        """完了したクリップは処理中の表示から除去される"""
        output = io.StringIO()
        r = ProgressRenderer(total=2, output=output)
        r._is_tty = True

        r.update(ClipProgress(clip_index=0, phase=ClipPhase.DOWNLOADING, percent=50.0))
        r.update(ClipProgress(clip_index=1, phase=ClipPhase.DOWNLOADING, percent=30.0))
        r.update(ClipProgress(clip_index=0, phase=ClipPhase.DONE))

        # After clip 0 is done, only clip 1 should be in active states
        active = {k: v for k, v in r._states.items() if v.phase not in (ClipPhase.DONE, ClipPhase.ERROR)}
        assert 0 not in active
        assert 1 in active


class TestFinishGuard:
    """finish()後の更新抑制テスト"""

    def test_update_after_finish_ignored(self) -> None:
        """finish()後のupdateは無視される"""
        output = io.StringIO()
        r = ProgressRenderer(total=1, output=output)
        r._is_tty = True
        r.update(ClipProgress(clip_index=0, phase=ClipPhase.DOWNLOADING, percent=50.0))
        r.finish()

        # Record output length after finish
        len_after_finish = len(output.getvalue())

        # This update should be silently ignored
        r.update(ClipProgress(clip_index=0, phase=ClipPhase.DOWNLOADING, percent=80.0))
        assert len(output.getvalue()) == len_after_finish


class TestThreadSafety:
    """スレッドセーフ性のテスト"""

    def test_concurrent_updates_no_crash(self) -> None:
        """並列updateでクラッシュしない"""
        import threading

        output = io.StringIO()
        r = ProgressRenderer(total=4, output=output)
        r._is_tty = True

        errors: list[Exception] = []

        def worker(idx: int) -> None:
            try:
                for pct in range(0, 100, 10):
                    r.update(ClipProgress(
                        clip_index=idx,
                        phase=ClipPhase.DOWNLOADING,
                        percent=float(pct),
                    ))
                r.update(ClipProgress(clip_index=idx, phase=ClipPhase.DONE))
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        assert r._completed == 4
