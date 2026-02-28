"""Cookie CLIコマンドのテスト"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from kirinuki.cli.main import cli
from kirinuki.core.cookie_service import CookieStatus


@pytest.fixture
def runner():
    return CliRunner()


class TestCookieSet:
    @patch("kirinuki.cli.cookie.CookieService")
    def test_set_from_stdin(self, mock_service_cls, runner):
        mock_service = MagicMock()
        mock_service_cls.return_value = mock_service

        result = runner.invoke(cli, ["cookie", "set"], input="# Netscape\n.youtube.com\tTRUE\n")
        assert result.exit_code == 0
        mock_service.save.assert_called_once()
        assert "保存しました" in result.output

    @patch("kirinuki.cli.cookie.CookieService")
    def test_set_empty_input_shows_error(self, mock_service_cls, runner):
        mock_service = MagicMock()
        mock_service.save.side_effect = ValueError("cookiesの内容が空です")
        mock_service_cls.return_value = mock_service

        result = runner.invoke(cli, ["cookie", "set"], input="")
        assert result.exit_code == 1
        assert "空" in result.output


class TestCookieStatus:
    @patch("kirinuki.cli.cookie.CookieService")
    def test_status_when_exists(self, mock_service_cls, runner):
        mock_service = MagicMock()
        mock_service.status.return_value = CookieStatus(
            exists=True,
            updated_at=datetime(2026, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
        )
        mock_service_cls.return_value = mock_service

        result = runner.invoke(cli, ["cookie", "status"])
        assert result.exit_code == 0
        assert "設定済み" in result.output
        assert "2026" in result.output

    @patch("kirinuki.cli.cookie.CookieService")
    def test_status_when_not_exists(self, mock_service_cls, runner):
        mock_service = MagicMock()
        mock_service.status.return_value = CookieStatus(exists=False, updated_at=None)
        mock_service_cls.return_value = mock_service

        result = runner.invoke(cli, ["cookie", "status"])
        assert result.exit_code == 0
        assert "未設定" in result.output


class TestCookieDelete:
    @patch("kirinuki.cli.cookie.CookieService")
    def test_delete_with_confirmation(self, mock_service_cls, runner):
        mock_service = MagicMock()
        mock_service_cls.return_value = mock_service

        result = runner.invoke(cli, ["cookie", "delete"], input="y\n")
        assert result.exit_code == 0
        mock_service.delete.assert_called_once()
        assert "削除しました" in result.output

    @patch("kirinuki.cli.cookie.CookieService")
    def test_delete_cancelled(self, mock_service_cls, runner):
        mock_service = MagicMock()
        mock_service_cls.return_value = mock_service

        result = runner.invoke(cli, ["cookie", "delete"], input="n\n")
        assert result.exit_code == 1
        mock_service.delete.assert_not_called()

    @patch("kirinuki.cli.cookie.CookieService")
    def test_delete_when_not_exists(self, mock_service_cls, runner):
        mock_service = MagicMock()
        mock_service.delete.side_effect = FileNotFoundError("cookiesが設定されていません")
        mock_service_cls.return_value = mock_service

        result = runner.invoke(cli, ["cookie", "delete"], input="y\n")
        assert result.exit_code == 1
        assert "設定されていません" in result.output


class TestCookieHelp:
    def test_cookie_help(self, runner):
        result = runner.invoke(cli, ["cookie", "--help"])
        assert result.exit_code == 0
        assert "cookie" in result.output.lower()
