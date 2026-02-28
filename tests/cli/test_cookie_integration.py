"""Cookie CLIコマンドのインテグレーションテスト（実ファイルシステム使用）"""

from unittest.mock import patch

import pytest
from click.testing import CliRunner

from kirinuki.cli.main import cli
from kirinuki.core.cookie_service import COOKIE_FILE_PATH


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def cookie_path(tmp_path):
    return tmp_path / "cookies.txt"


class TestCookieSetIntegration:
    def test_set_saves_file_to_disk(self, runner, cookie_path):
        cookie_content = "# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tTRUE\t0\tSID\tabc"

        with patch("kirinuki.cli.cookie.CookieService") as mock_cls:
            from kirinuki.core.cookie_service import CookieService

            service = CookieService(cookie_path=cookie_path)
            mock_cls.return_value = service

            result = runner.invoke(cli, ["cookie", "set"], input=cookie_content)

        assert result.exit_code == 0
        assert "保存しました" in result.output
        assert cookie_path.exists()
        assert cookie_path.read_text() == cookie_content

    def test_set_empty_input_does_not_save(self, runner, cookie_path):
        with patch("kirinuki.cli.cookie.CookieService") as mock_cls:
            from kirinuki.core.cookie_service import CookieService

            service = CookieService(cookie_path=cookie_path)
            mock_cls.return_value = service

            result = runner.invoke(cli, ["cookie", "set"], input="")

        assert result.exit_code == 1
        assert "空" in result.output
        assert not cookie_path.exists()


class TestCookieStatusIntegration:
    def test_status_shows_exists_with_date(self, runner, cookie_path):
        cookie_path.write_text("cookie data")

        with patch("kirinuki.cli.cookie.CookieService") as mock_cls:
            from kirinuki.core.cookie_service import CookieService

            service = CookieService(cookie_path=cookie_path)
            mock_cls.return_value = service

            result = runner.invoke(cli, ["cookie", "status"])

        assert result.exit_code == 0
        assert "設定済み" in result.output

    def test_status_shows_not_exists(self, runner, cookie_path):
        with patch("kirinuki.cli.cookie.CookieService") as mock_cls:
            from kirinuki.core.cookie_service import CookieService

            service = CookieService(cookie_path=cookie_path)
            mock_cls.return_value = service

            result = runner.invoke(cli, ["cookie", "status"])

        assert result.exit_code == 0
        assert "未設定" in result.output


class TestCookieDeleteIntegration:
    def test_delete_removes_file(self, runner, cookie_path):
        cookie_path.write_text("cookie data")

        with patch("kirinuki.cli.cookie.CookieService") as mock_cls:
            from kirinuki.core.cookie_service import CookieService

            service = CookieService(cookie_path=cookie_path)
            mock_cls.return_value = service

            result = runner.invoke(cli, ["cookie", "delete"], input="y\n")

        assert result.exit_code == 0
        assert "削除しました" in result.output
        assert not cookie_path.exists()

    def test_delete_cancel_preserves_file(self, runner, cookie_path):
        cookie_path.write_text("cookie data")

        with patch("kirinuki.cli.cookie.CookieService") as mock_cls:
            from kirinuki.core.cookie_service import CookieService

            service = CookieService(cookie_path=cookie_path)
            mock_cls.return_value = service

            result = runner.invoke(cli, ["cookie", "delete"], input="n\n")

        assert result.exit_code == 1
        assert cookie_path.exists()
