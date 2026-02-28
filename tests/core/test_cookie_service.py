"""CookieServiceのユニットテスト"""

import os
import stat

import pytest

from kirinuki.core.cookie_service import CookieService, CookieStatus


class TestSave:
    def test_save_creates_file_with_content(self, tmp_path):
        cookie_path = tmp_path / "cookies.txt"
        service = CookieService(cookie_path=cookie_path)
        content = "# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tTRUE\t0\tSID\tabc123"

        service.save(content)

        assert cookie_path.exists()
        assert cookie_path.read_text() == content

    def test_save_raises_on_empty_string(self, tmp_path):
        cookie_path = tmp_path / "cookies.txt"
        service = CookieService(cookie_path=cookie_path)

        with pytest.raises(ValueError):
            service.save("")

    def test_save_raises_on_whitespace_only(self, tmp_path):
        cookie_path = tmp_path / "cookies.txt"
        service = CookieService(cookie_path=cookie_path)

        with pytest.raises(ValueError):
            service.save("   \n\t  ")

    def test_save_creates_parent_directory(self, tmp_path):
        cookie_path = tmp_path / "nested" / "dir" / "cookies.txt"
        service = CookieService(cookie_path=cookie_path)

        service.save("cookie content")

        assert cookie_path.exists()
        assert cookie_path.read_text() == "cookie content"

    def test_save_overwrites_existing_file(self, tmp_path):
        cookie_path = tmp_path / "cookies.txt"
        cookie_path.write_text("old content")
        service = CookieService(cookie_path=cookie_path)

        service.save("new content")

        assert cookie_path.read_text() == "new content"

    def test_save_sets_file_permissions_600(self, tmp_path):
        cookie_path = tmp_path / "cookies.txt"
        service = CookieService(cookie_path=cookie_path)

        service.save("cookie content")

        if os.name != "nt":
            file_stat = cookie_path.stat()
            assert stat.S_IMODE(file_stat.st_mode) == 0o600


class TestStatus:
    def test_status_when_file_exists(self, tmp_path):
        cookie_path = tmp_path / "cookies.txt"
        cookie_path.write_text("cookie data")
        service = CookieService(cookie_path=cookie_path)

        result = service.status()

        assert isinstance(result, CookieStatus)
        assert result.exists is True
        assert result.updated_at is not None

    def test_status_when_file_not_exists(self, tmp_path):
        cookie_path = tmp_path / "cookies.txt"
        service = CookieService(cookie_path=cookie_path)

        result = service.status()

        assert isinstance(result, CookieStatus)
        assert result.exists is False
        assert result.updated_at is None


class TestDelete:
    def test_delete_removes_file(self, tmp_path):
        cookie_path = tmp_path / "cookies.txt"
        cookie_path.write_text("cookie data")
        service = CookieService(cookie_path=cookie_path)

        service.delete()

        assert not cookie_path.exists()

    def test_delete_raises_when_file_not_exists(self, tmp_path):
        cookie_path = tmp_path / "cookies.txt"
        service = CookieService(cookie_path=cookie_path)

        with pytest.raises(FileNotFoundError):
            service.delete()
