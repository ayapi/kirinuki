"""進捗のターミナル描画"""

import os
import sys
import threading
import time
from typing import TextIO

from kirinuki.models.clip import ClipPhase, ClipProgress


def _detect_tty(output: TextIO) -> bool:
    """出力先がターミナルかどうかを判定する。

    MSYS2/MinTTYではisatty()がFalseを返すため、
    MSYSTEM環境変数とTERM環境変数で補完判定する。

    Note: MSYS2フォールバックは標準ストリーム（stdout/stderr）のみに適用。
    シェルリダイレクト（2>file）時はTERMが維持されるためANSIが混入しうるが、
    MinTTYのpty判定にはWindows API（名前付きパイプ検査）が必要で過度に複雑。
    """
    if hasattr(output, "isatty") and output.isatty():
        return True
    # MSYS2フォールバックは標準ストリームのみに適用
    if output not in (sys.stdout, sys.stderr):
        return False
    # MSYS2/MinTTY: isatty()=False だが実際はターミナル接続
    msystem = os.environ.get("MSYSTEM")
    term = os.environ.get("TERM", "")
    if msystem and term and term != "dumb":
        return True
    return False


def _enable_windows_vt() -> None:
    """WindowsコンソールでVT100エスケープシーケンスを有効化する。"""
    if sys.platform == "win32":
        os.system("")


def _format_bytes(n: int) -> str:
    """バイト数を人間可読な文字列にフォーマットする。"""
    if n >= 1_000_000_000:
        return f"{n / 1_000_000_000:.1f}GB"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}MB"
    if n >= 1_000:
        return f"{n / 1_000:.1f}KB"
    return f"{n}B"


def _format_eta(seconds: int) -> str:
    """残り秒数を M:SS 形式にフォーマットする。"""
    m, s = divmod(seconds, 60)
    return f"{m}:{s:02d}"


class ProgressRenderer:
    """複数クリップの進捗をANSIエスケープで描画する。"""

    _SPINNER_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
    _SPIN_INTERVAL = 0.12  # seconds

    def __init__(self, total: int, output: TextIO = sys.stderr) -> None:
        self._total = total
        self._output = output
        self._is_tty: bool = _detect_tty(output)
        if self._is_tty:
            _enable_windows_vt()
        self._states: dict[int, ClipProgress] = {}
        self._completed: int = 0
        self._lines_written: int = 0
        self._finished: bool = False
        self._lock = threading.Lock()
        self._spinner_idx: int = 0
        self._spinner_thread: threading.Thread | None = None

    def _current_spinner(self) -> str:
        return self._SPINNER_FRAMES[self._spinner_idx % len(self._SPINNER_FRAMES)]

    def _format_line(
        self, progress: ClipProgress, spinner_char: str = ""
    ) -> str:
        """ClipProgressから1行の進捗文字列を生成する。"""
        if progress.phase == ClipPhase.DONE:
            return "完了"
        if progress.phase == ClipPhase.ERROR:
            return "エラー"

        s = f"{spinner_char} " if spinner_char else ""
        if progress.phase == ClipPhase.REENCODING:
            return f"{s}再エンコード中..."

        # DOWNLOADING
        parts: list[str] = [f"{s}ダウンロード中"]

        if progress.percent is not None:
            parts.append(f"{progress.percent:.1f}%")

        size_parts: list[str] = []
        if progress.downloaded_bytes is not None:
            size_parts.append(_format_bytes(progress.downloaded_bytes))
        if progress.total_bytes is not None:
            size_parts.append(_format_bytes(progress.total_bytes))
        if size_parts:
            parts.append("/".join(size_parts))

        if progress.speed is not None:
            parts.append(f"{_format_bytes(int(progress.speed))}/s")

        if progress.eta is not None:
            parts.append(f"ETA {_format_eta(progress.eta)}")

        return " | ".join(parts)

    def _start_spinner(self) -> None:
        """スピナースレッドを開始する（まだ開始していなければ）。"""
        if self._spinner_thread is not None:
            return

        def _spin() -> None:
            while not self._finished:
                time.sleep(self._SPIN_INTERVAL)
                with self._lock:
                    if self._finished:
                        break
                    self._spinner_idx += 1
                    if self._states:
                        self._render()

        t = threading.Thread(target=_spin, daemon=True)
        t.start()
        self._spinner_thread = t

    def update(self, progress: ClipProgress) -> None:
        """進捗を更新して再描画する。"""
        if not self._is_tty:
            return

        with self._lock:
            if self._finished:
                return

            # 完了カウント更新
            prev = self._states.get(progress.clip_index)
            if (
                progress.phase in (ClipPhase.DONE, ClipPhase.ERROR)
                and (prev is None or prev.phase not in (ClipPhase.DONE, ClipPhase.ERROR))
            ):
                self._completed += 1

            self._states[progress.clip_index] = progress
            self._render()

        self._start_spinner()

    def _render(self) -> None:
        """現在の状態をターミナルに描画する。"""
        # 初回描画時にカーソルを非表示にする
        if self._lines_written == 0:
            self._output.write("\033[?25l")

        # カーソルを前回描画行数分戻す
        if self._lines_written > 0:
            self._output.write(f"\033[{self._lines_written}A")

        lines: list[str] = []
        spin = self._current_spinner()

        if self._total == 1:
            # 単一クリップ: 1行のみ
            if self._states:
                p = next(iter(self._states.values()))
                lines.append(self._format_line(p, spinner_char=spin))
        else:
            # マルチクリップ: ヘッダー + 処理中クリップ
            lines.append(f"[{self._completed}/{self._total}] 完了")
            for idx in sorted(self._states):
                p = self._states[idx]
                if p.phase in (ClipPhase.DONE, ClipPhase.ERROR):
                    continue
                lines.append(
                    f"  #{idx + 1} {self._format_line(p, spinner_char=spin)}"
                )

        # 各行をクリアして書き込み
        buf = ""
        for line in lines:
            buf += f"\033[2K{line}\n"

        # 前回より行数が減った場合、残り行をクリア
        for _ in range(self._lines_written - len(lines)):
            buf += "\033[2K\n"

        self._output.write(buf)
        self._output.flush()
        self._lines_written = max(len(lines), self._lines_written)

    def finish(self) -> None:
        """進捗行をクリアしてカーソル位置を復元する。"""
        if not self._is_tty:
            return

        with self._lock:
            self._finished = True
            if self._lines_written > 0:
                self._output.write(f"\033[{self._lines_written}A")
                for _ in range(self._lines_written):
                    self._output.write("\033[2K\n")
                self._output.write(f"\033[{self._lines_written}A")
            # カーソルを再表示
            self._output.write("\033[?25h")
            self._output.flush()
            self._lines_written = 0

        # スピナースレッドの停止を待つ
        if self._spinner_thread is not None:
            self._spinner_thread.join(timeout=1.0)
            self._spinner_thread = None
