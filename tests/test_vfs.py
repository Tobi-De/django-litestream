from __future__ import annotations

import os
import platform
import sqlite3
import sys
from pathlib import Path
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
from django.test import override_settings


class TestVfsSettings:
    def test_extension_linux(self):
        with patch.object(platform, "system", return_value="Linux"):
            from django_litestream_vfs.conf import VfsSettings

            expected = Path(sys.executable).parent / "litestream.so"
            assert VfsSettings().vfs_extension_path == expected

    def test_extension_macos(self):
        with patch.object(platform, "system", return_value="Darwin"):
            from django_litestream_vfs.conf import VfsSettings

            expected = Path(sys.executable).parent / "litestream.dylib"
            assert VfsSettings().vfs_extension_path == expected

    def test_extension_custom(self):
        with override_settings(
            LITESTREAM={"vfs_extension_path": "/opt/vfs/litestream.so"}
        ):
            from django_litestream_vfs.conf import VfsSettings

            assert VfsSettings().vfs_extension_path == Path("/opt/vfs/litestream.so")

    def test_bin_path_default(self):
        from django_litestream_vfs.conf import VfsSettings

        expected = Path(sys.executable).parent / "litestream"
        assert VfsSettings().bin_path == expected

    def test_bin_path_custom(self):
        with override_settings(LITESTREAM={"bin_path": "/opt/bin/litestream"}):
            from django_litestream_vfs.conf import VfsSettings

            assert VfsSettings().bin_path == Path("/opt/bin/litestream")

    def test_extension_resolves_relative_to_bin(self):
        with override_settings(LITESTREAM={"bin_path": "/opt/bin/litestream"}):
            with patch.object(platform, "system", return_value="Linux"):
                from django_litestream_vfs.conf import VfsSettings

                assert VfsSettings().vfs_extension_path == Path(
                    "/opt/bin/litestream.so"
                )


class TestEnsureVfsLoaded:
    def test_raises_when_file_missing(self, tmp_path):
        from django_litestream_vfs import loader

        loader._vfs_loaded = False
        fake_path = str(tmp_path / "nonexistent.so")
        with override_settings(LITESTREAM={"vfs_extension_path": fake_path}):
            with pytest.raises(
                FileNotFoundError, match="Litestream VFS extension not found"
            ):
                loader.ensure_vfs_loaded()

    def test_loads_via_ctypes_auto_extension(self, tmp_path):
        from django_litestream_vfs import loader

        loader._vfs_loaded = False
        fake_so = tmp_path / "litestream.so"
        fake_so.write_bytes(b"\x7fELF")

        mock_sqlite = MagicMock()
        mock_sqlite.sqlite3_auto_extension.return_value = 0
        mock_vfs = MagicMock()

        with override_settings(LITESTREAM={"vfs_extension_path": str(fake_so)}):
            with patch(
                "ctypes.util.find_library", return_value="/usr/lib/libsqlite3.so"
            ), patch("ctypes.CDLL", side_effect=[mock_sqlite, mock_vfs]), patch(
                "ctypes.c_void_p.in_dll", return_value=12345
            ):
                loader.ensure_vfs_loaded()
        assert loader._vfs_loaded is True

    def test_idempotent_second_call_noop(self, tmp_path):
        from django_litestream_vfs import loader

        loader._vfs_loaded = False
        fake_so = tmp_path / "litestream.so"
        fake_so.write_bytes(b"\x7fELF")

        calls = []

        def mock_cdll(*args, **kwargs):
            m = MagicMock()
            m.sqlite3_auto_extension.return_value = 0
            calls.append(1)
            return m

        with override_settings(LITESTREAM={"vfs_extension_path": str(fake_so)}):
            with patch(
                "ctypes.util.find_library", return_value="/usr/lib/libsqlite3.so"
            ), patch("ctypes.CDLL", side_effect=mock_cdll), patch(
                "ctypes.c_void_p.in_dll", return_value=12345
            ):
                loader.ensure_vfs_loaded()
                loader.ensure_vfs_loaded()
                assert len(calls) == 2  # CDLL called exactly twice, no third call

    def test_raises_runtime_error_on_load_failure(self, tmp_path):
        from django_litestream_vfs import loader

        loader._vfs_loaded = False
        fake_so = tmp_path / "litestream.so"
        fake_so.write_bytes(b"\x7fELF")

        with override_settings(LITESTREAM={"vfs_extension_path": str(fake_so)}):
            with patch("ctypes.CDLL", side_effect=OSError("dlopen failed")):
                with pytest.raises(
                    RuntimeError, match="Failed to load Litestream VFS extension"
                ):
                    loader.ensure_vfs_loaded()

    def test_thread_safe_single_load(self, tmp_path):
        from django_litestream_vfs import loader

        loader._vfs_loaded = False
        fake_so = tmp_path / "litestream.so"
        fake_so.write_bytes(b"\x7fELF")

        import concurrent.futures

        def mock_cdll(*args, **kwargs):
            m = MagicMock()
            m.sqlite3_auto_extension.return_value = 0
            return m

        with override_settings(LITESTREAM={"vfs_extension_path": str(fake_so)}):
            with patch(
                "ctypes.util.find_library", return_value="/usr/lib/libsqlite3.so"
            ), patch("ctypes.CDLL", side_effect=mock_cdll), patch(
                "ctypes.c_void_p.in_dll", return_value=12345
            ):
                with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
                    list(ex.map(lambda _: loader.ensure_vfs_loaded(), range(4)))
        assert loader._vfs_loaded is True


class TestGetVfsDatabases:
    def test_generates_config(self):
        from django_litestream_vfs import get_vfs_databases

        with override_settings(LITESTREAM={"vfs": {"prod": "s3://bucket/db.sqlite3"}}):
            dbs = get_vfs_databases()
            assert dbs["prod"]["ENGINE"] == "django_litestream_vfs.backends.sqlite_vfs"
            assert dbs["prod"]["OPTIONS"]["uri"] is True
            assert (
                dbs["prod"]["OPTIONS"]["litestream_replica_url"]
                == "s3://bucket/db.sqlite3"
            )
            assert "vfs=litestream&mode=ro" in dbs["prod"]["NAME"]

    def test_empty_when_no_vfs_config(self):
        from django_litestream_vfs import get_vfs_databases

        with override_settings(LITESTREAM={}):
            assert get_vfs_databases() == {}

    def test_skips_non_string_values(self):
        from django_litestream_vfs import get_vfs_databases

        with override_settings(
            LITESTREAM={"vfs": {"valid": "s3://bucket/db", "skip": 123}}
        ):
            dbs = get_vfs_databases()
            assert "valid" in dbs
            assert "skip" not in dbs

    def test_multiple_replicas(self):
        from django_litestream_vfs import get_vfs_databases

        with override_settings(
            LITESTREAM={
                "vfs": {
                    "prod": "s3://bucket/prod.db",
                    "analytics": "gcs://bucket/analytics.db",
                }
            }
        ):
            dbs = get_vfs_databases()
            assert len(dbs) == 2


class TestVfsConfig:
    def test_ready_is_noop(self):
        """ready() does nothing -- VFS is loaded by the backend on first query."""
        import django_litestream_vfs

        with override_settings(LITESTREAM={}):
            with patch("django_litestream_vfs.loader.ensure_vfs_loaded") as mock_load:
                from django_litestream_vfs.apps import VfsConfig

                config = VfsConfig("django_litestream_vfs", django_litestream_vfs)
                config.ready()
                mock_load.assert_not_called()


class TestDatabaseWrapper:
    def test_sets_env_var_and_loads_vfs(self):
        from django_litestream_vfs.backends.sqlite_vfs import DatabaseWrapper

        wrapper = DatabaseWrapper(
            {
                "ENGINE": "django_litestream_vfs.backends.sqlite_vfs",
                "NAME": "file:test.db?vfs=litestream&mode=ro",
                "OPTIONS": {
                    "uri": True,
                    "litestream_replica_url": "s3://bucket/db.sqlite3",
                },
            }
        )

        with patch(
            "django_litestream_vfs.backends.sqlite_vfs.base.ensure_vfs_loaded"
        ) as mock_load:
            with patch.object(wrapper, "get_connection_params", return_value={}):
                with patch(
                    "django.db.backends.sqlite3.base.DatabaseWrapper.get_new_connection",
                    return_value=MagicMock(),
                ):
                    wrapper.get_new_connection({})

        mock_load.assert_called_once()
        assert os.environ.get("LITESTREAM_REPLICA_URL") == "s3://bucket/db.sqlite3"

    def test_does_not_set_env_var_when_no_replica_url(self):
        from django_litestream_vfs.backends.sqlite_vfs import DatabaseWrapper

        os.environ.pop("LITESTREAM_REPLICA_URL", None)

        wrapper = DatabaseWrapper(
            {
                "ENGINE": "django_litestream_vfs.backends.sqlite_vfs",
                "NAME": "file:test.db?vfs=litestream",
                "OPTIONS": {"uri": True},
            }
        )

        with patch("django_litestream_vfs.backends.sqlite_vfs.base.ensure_vfs_loaded"):
            with patch.object(wrapper, "get_connection_params", return_value={}):
                with patch(
                    "django.db.backends.sqlite3.base.DatabaseWrapper.get_new_connection",
                    return_value=MagicMock(),
                ):
                    wrapper.get_new_connection({})

        assert "LITESTREAM_REPLICA_URL" not in os.environ
