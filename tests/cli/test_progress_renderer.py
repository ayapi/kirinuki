"""ProgressRenderer のユニットテスト"""

import io
from unittest.mock import patch

from kirinuki.cli.progress_renderer import ProgressRenderer, _detect_tty
from kirinuki.models.clip import ClipPhase, ClipProgress


class TestDetectTty:
    """_detect_tty のテスト"""

    def test_real_tty_returns_true(self) -> None:
        """isatty()=True なら True"""
        output = io.StringIO()
        output.isatty = lambda: True  # type: ignore[assignment]
        assert _detect_tty(output) is True

    def test_non_tty_non_msys_returns_false(self) -> None:
        """isatty()=False かつ MSYSTEM 未設定なら False"""
        output = io.StringIO()
        with patch.dict("os.environ", {}, clear=True):
            assert _detect_tty(output) is False

    def test_msys2_mintty_returns_true(self) -> None:
        """isatty()=False でも MSYSTEM 設定 + TERM が dumb 以外 + 標準ストリームなら True"""
        import sys

        env = {"MSYSTEM": "MINGW64", "TERM": "xterm-256color"}
        with patch.dict("os.environ", env, clear=True):
            assert _detect_tty(sys.stderr) is True

    def test_msys2_dumb_term_returns_false(self) -> None:
        """MSYSTEM 設定済みでも TERM=dumb なら False（パイプリダイレクト）"""
        output = io.StringIO()
        env = {"MSYSTEM": "MINGW64", "TERM": "dumb"}
        with patch.dict("os.environ", env, clear=True):
            assert _detect_tty(output) is False

    def test_msys2_no_term_returns_false(self) -> None:
        """MSYSTEM 設定済みでも TERM 未設定なら False"""
        output = io.StringIO()
        env = {"MSYSTEM": "MINGW64"}
        with patch.dict("os.environ", env, clear=True):
            assert _detect_tty(output) is False

    def test_msys2_non_standard_stream_returns_false(self) -> None:
        """MSYS2環境でも標準ストリーム以外なら False"""
        output = io.StringIO()  # 非標準ストリーム
        env = {"MSYSTEM": "MINGW64", "TERM": "xterm-256color"}
        with patch.dict("os.environ", env, clear=True):
            assert _detect_tty(output) is False

    def test_msys2_stderr_returns_true(self) -> None:
        """MSYS2環境で sys.stderr なら True"""
        import sys

        env = {"MSYSTEM": "MINGW64", "TERM": "xterm-256color"}
        with patch.dict("os.environ", env, clear=True):
            assert _detect_tty(sys.stderr) is True


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


class TestSpinner:
    """スピナーアニメーションのテスト"""

    def test_active_phase_has_spinner(self) -> None:
        """ダウンロード中・再エンコード中にスピナー文字が含まれる"""
        output = io.StringIO()
        r = ProgressRenderer(total=1, output=output)
        r._is_tty = True

        r.update(ClipProgress(clip_index=0, phase=ClipPhase.DOWNLOADING))
        content = output.getvalue()
        # スピナーフレームのいずれかが含まれる
        assert any(c in content for c in ProgressRenderer._SPINNER_FRAMES)

    def test_done_phase_no_spinner(self) -> None:
        """完了フェーズにスピナーが含まれない"""
        r = ProgressRenderer(total=1, output=io.StringIO())
        p = ClipProgress(clip_index=0, phase=ClipPhase.DONE)
        line = r._format_line(p, spinner_char="⠋")
        assert "⠋" not in line

    def test_spinner_advances_on_tick(self) -> None:
        """_tickでスピナーフレームが進む"""
        output = io.StringIO()
        r = ProgressRenderer(total=1, output=output)
        r._is_tty = True

        r.update(ClipProgress(clip_index=0, phase=ClipPhase.DOWNLOADING))
        first = output.getvalue()

        # Manually advance spinner
        r._spinner_idx = 1
        output.truncate(0)
        output.seek(0)
        r.update(ClipProgress(clip_index=0, phase=ClipPhase.DOWNLOADING))
        second = output.getvalue()

        # Different spinner frame should be used
        assert first != second

    def test_spinner_thread_stops_on_finish(self) -> None:
        """finish()後にスピナースレッドが停止する"""
        import time

        output = io.StringIO()
        r = ProgressRenderer(total=1, output=output)
        r._is_tty = True

        r.update(ClipProgress(clip_index=0, phase=ClipPhase.DOWNLOADING))
        time.sleep(0.3)  # スピナースレッドが起動する時間
        r.finish()
        time.sleep(0.2)
        assert r._finished is True


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
