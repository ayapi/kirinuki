"""進捗のターミナル描画"""

import os
import sys
import threading
from typing import TextIO

from kirinuki.models.clip import ClipPhase, ClipProgress


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

    def __init__(self, total: int, output: TextIO = sys.stderr) -> None:
        self._total = total
        self._output = output
        self._is_tty: bool = hasattr(output, "isatty") and output.isatty()
        if self._is_tty:
            _enable_windows_vt()
        self._states: dict[int, ClipProgress] = {}
        self._completed: int = 0
        self._lines_written: int = 0
        self._finished: bool = False
        self._lock = threading.Lock()

    def _format_line(self, progress: ClipProgress) -> str:
        """ClipProgressから1行の進捗文字列を生成する。"""
        if progress.phase == ClipPhase.DONE:
            return "完了"
        if progress.phase == ClipPhase.REENCODING:
            return "再エンコード中..."
        if progress.phase == ClipPhase.ERROR:
            return "エラー"

        # DOWNLOADING
        parts: list[str] = ["ダウンロード中"]

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

    def _render(self) -> None:
        """現在の状態をターミナルに描画する。"""
        # カーソルを前回描画行数分戻す
        if self._lines_written > 0:
            self._output.write(f"\033[{self._lines_written}A")

        lines: list[str] = []

        if self._total == 1:
            # 単一クリップ: 1行のみ
            if self._states:
                p = next(iter(self._states.values()))
                lines.append(self._format_line(p))
        else:
            # マルチクリップ: ヘッダー + 処理中クリップ
            lines.append(f"[{self._completed}/{self._total}] 完了")
            for idx in sorted(self._states):
                p = self._states[idx]
                if p.phase in (ClipPhase.DONE, ClipPhase.ERROR):
                    continue
                lines.append(f"  #{idx + 1} {self._format_line(p)}")

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
            if self._lines_written > 0:
                self._output.write(f"\033[{self._lines_written}A")
                for _ in range(self._lines_written):
                    self._output.write("\033[2K\n")
                self._output.write(f"\033[{self._lines_written}A")
                self._output.flush()
            self._lines_written = 0
            self._finished = True
