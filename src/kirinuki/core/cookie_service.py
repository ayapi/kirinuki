"""Cookie管理サービス"""

import getpass
import logging
import os
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

COOKIE_FILE_PATH: Path = Path.home() / ".kirinuki" / "cookies.txt"


@dataclass(frozen=True)
class CookieStatus:
    exists: bool
    updated_at: datetime | None


class CookieService:
    def __init__(self, cookie_path: Path = COOKIE_FILE_PATH) -> None:
        self._cookie_path = cookie_path

    def save(self, content: str) -> None:
        """cookiesの内容をファイルに保存する。

        Raises:
            ValueError: contentが空または空白のみの場合
        """
        if not content.strip():
            raise ValueError("cookiesの内容が空です")

        self._cookie_path.parent.mkdir(parents=True, exist_ok=True)
        self._cookie_path.write_text(content)

        if os.name == "nt":
            self._restrict_acl_windows(self._cookie_path)
        else:
            os.chmod(self._cookie_path, 0o600)

    @staticmethod
    def _restrict_acl_windows(path: Path) -> None:
        """Windows環境でファイルのACLを現在のユーザーのみに制限する。"""
        try:
            username = getpass.getuser()
        except Exception:
            logger.warning("ユーザー名を取得できません。ACLの設定をスキップします。")
            return

        try:
            result = subprocess.run(
                ["icacls", str(path), "/inheritance:r", "/grant:r", f"{username}:(R,W)"],
                capture_output=True, text=True,
            )
            if result.returncode != 0:
                logger.warning("icaclsによるACL設定に失敗しました: %s", result.stderr.strip())
        except OSError as e:
            logger.warning("icaclsの実行に失敗しました: %s", e)

    def status(self) -> CookieStatus:
        """cookies.txtの状態を返す。"""
        if not self._cookie_path.exists():
            return CookieStatus(exists=False, updated_at=None)

        mtime = self._cookie_path.stat().st_mtime
        updated_at = datetime.fromtimestamp(mtime, tz=timezone.utc)
        return CookieStatus(exists=True, updated_at=updated_at)

    def delete(self) -> None:
        """cookies.txtを削除する。

        Raises:
            FileNotFoundError: ファイルが存在しない場合
        """
        if not self._cookie_path.exists():
            raise FileNotFoundError("cookiesが設定されていません")

        self._cookie_path.unlink()
