from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
from django.test import override_settings

from django_litestream.conf import app_settings


class TestVfsSettings:
    def test_extension_defaults_to_upstream_loadable_path(self):
        from litestream_vfs import loadable_path

        from django_litestream_vfs.conf import VfsSettings

        assert VfsSettings().vfs_extension_path == Path(loadable_path())

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

    def test_loads_via_sql_function(self, tmp_path):
        from django_litestream_vfs import loader

        loader._vfs_loaded = False
        fake_so = tmp_path / "litestream.so"
        fake_so.write_bytes(b"\x7fELF")

        mock_conn = MagicMock()
        mock_conn.load_extension.side_effect = TypeError  # force SQL fallback
        with override_settings(LITESTREAM={"vfs_extension_path": str(fake_so)}):
            with patch("sqlite3.connect", return_value=mock_conn):
                loader.ensure_vfs_loaded()
        mock_conn.enable_load_extension.assert_called_with(True)
        mock_conn.close.assert_called_once()
        assert loader._vfs_loaded is True

    def test_idempotent_second_call_noop(self, tmp_path):
        from django_litestream_vfs import loader

        loader._vfs_loaded = False
        fake_so = tmp_path / "litestream.so"
        fake_so.write_bytes(b"\x7fELF")

        mock_conn = MagicMock()
        mock_conn.load_extension.side_effect = TypeError
        with override_settings(LITESTREAM={"vfs_extension_path": str(fake_so)}):
            with patch("sqlite3.connect", return_value=mock_conn):
                loader.ensure_vfs_loaded()
                loader.ensure_vfs_loaded()
        assert mock_conn.execute.call_count == 1
        assert loader._vfs_loaded is True

    def test_raises_runtime_error_on_load_failure(self, tmp_path):
        from django_litestream_vfs import loader

        loader._vfs_loaded = False
        fake_so = tmp_path / "litestream.so"
        fake_so.write_bytes(b"\x7fELF")

        mock_conn = MagicMock()
        mock_conn.load_extension.side_effect = TypeError
        mock_conn.execute.side_effect = sqlite3.OperationalError("bad extension")
        with override_settings(LITESTREAM={"vfs_extension_path": str(fake_so)}):
            with patch("sqlite3.connect", return_value=mock_conn):
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

        mock_conn = MagicMock()
        mock_conn.load_extension.side_effect = TypeError
        with override_settings(LITESTREAM={"vfs_extension_path": str(fake_so)}):
            with patch("sqlite3.connect", return_value=mock_conn):
                with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
                    list(ex.map(lambda _: loader.ensure_vfs_loaded(), range(4)))
        assert mock_conn.execute.call_count == 1
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

    def test_replica_url_is_passed_per_connection(self):
        """The replica must live in the URI: the extension reads the env var once."""
        from urllib.parse import parse_qs, urlsplit

        from django_litestream_vfs import get_vfs_databases

        with override_settings(LITESTREAM={"vfs": {"prod": "s3://bucket/db.sqlite3"}}):
            name = get_vfs_databases()["prod"]["NAME"]
        assert name.startswith("file:prod.db?")
        query = parse_qs(urlsplit(name).query)
        assert query["vfs"] == ["litestream"]
        assert query["mode"] == ["ro"]
        assert query["replica_url"] == ["s3://bucket/db.sqlite3"]

    def test_each_alias_gets_its_own_replica_url(self):
        from urllib.parse import parse_qs, urlsplit

        from django_litestream_vfs import get_vfs_databases

        with override_settings(
            LITESTREAM={
                "vfs": {"prod": "s3://bucket/prod.db", "analytics": "gcs://b/a.db"}
            }
        ):
            dbs = get_vfs_databases()
        prod = parse_qs(urlsplit(dbs["prod"]["NAME"]).query)["replica_url"]
        analytics = parse_qs(urlsplit(dbs["analytics"]["NAME"]).query)["replica_url"]
        assert prod == ["s3://bucket/prod.db"]
        assert analytics == ["gcs://b/a.db"]

    def test_dict_entry_with_options(self):
        from urllib.parse import parse_qs, urlsplit

        from django_litestream_vfs import get_vfs_databases

        with override_settings(
            LITESTREAM={
                "vfs": {
                    "prod": {
                        "url": "s3://bucket/db.sqlite3?endpoint=example.com",
                        "poll_interval": "5s",
                        "cache_size": 33554432,
                    }
                }
            }
        ):
            name = get_vfs_databases()["prod"]["NAME"]
        query = parse_qs(urlsplit(name).query)
        assert query["replica_url"] == ["s3://bucket/db.sqlite3?endpoint=example.com"]
        assert query["poll_interval"] == ["5s"]
        assert query["cache_size"] == ["33554432"]

    def test_dict_entry_ignores_unknown_keys(self):
        from urllib.parse import parse_qs, urlsplit

        from django_litestream_vfs import get_vfs_databases

        with override_settings(
            LITESTREAM={"vfs": {"prod": {"url": "s3://b/db", "not_an_option": "x"}}}
        ):
            name = get_vfs_databases()["prod"]["NAME"]
        assert "not_an_option" not in parse_qs(urlsplit(name).query)

    def test_dict_entry_without_url_is_skipped(self):
        from django_litestream_vfs import get_vfs_databases

        with override_settings(LITESTREAM={"vfs": {"prod": {"poll_interval": "5s"}}}):
            assert get_vfs_databases() == {}

    def test_write_enabled_drops_read_only_mode(self):
        from urllib.parse import parse_qs, urlsplit

        from django_litestream_vfs import get_vfs_databases

        with override_settings(
            LITESTREAM={
                "vfs": {
                    "writable": {
                        "url": "s3://bucket/db.sqlite3",
                        "write_enabled": True,
                    }
                }
            }
        ):
            name = get_vfs_databases()["writable"]["NAME"]
        query = parse_qs(urlsplit(name).query)
        assert "mode" not in query
        assert query["write_enabled"] == ["true"]

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
        import django_litestream_vfs

        with override_settings(LITESTREAM={}):
            with patch("django_litestream_vfs.loader.ensure_vfs_loaded") as mock_load:
                from django_litestream_vfs.apps import VfsConfig

                config = VfsConfig("django_litestream_vfs", django_litestream_vfs)
                config.ready()
                mock_load.assert_not_called()


class TestDatabaseWrapper:
    def _connect(self, options):
        from django_litestream_vfs.backends.sqlite_vfs import DatabaseWrapper

        wrapper = DatabaseWrapper(
            {
                "ENGINE": "django_litestream_vfs.backends.sqlite_vfs",
                "NAME": "file:test.db?vfs=litestream&mode=ro",
                "OPTIONS": {"uri": True, **options},
            }
        )

        conn_params = wrapper.get_connection_params()
        with patch(
            "django_litestream_vfs.backends.sqlite_vfs.base.ensure_vfs_loaded"
        ) as mock_load:
            with patch(
                "django.db.backends.sqlite3.base.DatabaseWrapper.get_new_connection",
                return_value=MagicMock(),
            ) as mock_conn:
                wrapper.get_new_connection(conn_params)
        mock_load.assert_called_once()
        return mock_conn.call_args[0][0]

    def test_injects_replica_url_into_uri(self):
        from urllib.parse import parse_qs, urlsplit

        params = self._connect({"litestream_replica_url": "s3://bucket/db.sqlite3"})
        query = parse_qs(urlsplit(params["database"]).query)
        assert query["vfs"] == ["litestream"]
        assert query["mode"] == ["ro"]
        assert query["replica_url"] == ["s3://bucket/db.sqlite3"]

    def test_does_not_set_global_env_var(self):
        os.environ.pop("LITESTREAM_REPLICA_URL", None)
        self._connect({"litestream_replica_url": "s3://bucket/db.sqlite3"})
        assert "LITESTREAM_REPLICA_URL" not in os.environ

    def test_two_replicas_get_distinct_uris(self):
        from urllib.parse import parse_qs, urlsplit

        first = self._connect({"litestream_replica_url": "s3://bucket/one.db"})
        second = self._connect({"litestream_replica_url": "s3://bucket/two.db"})
        first_url = parse_qs(urlsplit(first["database"]).query)["replica_url"]
        second_url = parse_qs(urlsplit(second["database"]).query)["replica_url"]
        assert first_url == ["s3://bucket/one.db"]
        assert second_url == ["s3://bucket/two.db"]

    def test_does_not_override_existing_uri_param(self):
        from urllib.parse import parse_qs, urlsplit

        from django_litestream_vfs.backends.sqlite_vfs import DatabaseWrapper

        wrapper = DatabaseWrapper(
            {
                "ENGINE": "django_litestream_vfs.backends.sqlite_vfs",
                "NAME": "file:test.db?vfs=litestream&mode=ro&replica_url=s3%3A%2F%2Ffrom-uri",
                "OPTIONS": {
                    "uri": True,
                    "litestream_replica_url": "s3://from-options",
                },
            }
        )
        conn_params = wrapper.get_connection_params()
        with patch("django_litestream_vfs.backends.sqlite_vfs.base.ensure_vfs_loaded"):
            with patch(
                "django.db.backends.sqlite3.base.DatabaseWrapper.get_new_connection",
                return_value=MagicMock(),
            ) as mock_conn:
                wrapper.get_new_connection(conn_params)
        database = mock_conn.call_args[0][0]["database"]
        assert parse_qs(urlsplit(database).query)["replica_url"] == ["s3://from-uri"]

    def test_extra_vfs_options_are_forwarded(self):
        from urllib.parse import parse_qs, urlsplit

        params = self._connect(
            {
                "litestream_replica_url": "s3://bucket/db",
                "poll_interval": "5s",
                "cache_size": 1024,
            }
        )
        query = parse_qs(urlsplit(params["database"]).query)
        assert query["poll_interval"] == ["5s"]
        assert query["cache_size"] == ["1024"]

    def test_options_are_not_passed_to_sqlite(self):
        params = self._connect(
            {"litestream_replica_url": "s3://bucket/db", "poll_interval": "5s"}
        )
        assert "litestream_replica_url" not in params
        assert "poll_interval" not in params

    def test_no_replica_url_leaves_name_untouched(self):
        params = self._connect({})
        assert params["database"] == "file:test.db?vfs=litestream&mode=ro"


class TestVfsMultiReplicaIntegration:
    """End-to-end: two replicas opened in one process must not share a client."""

    def test_each_alias_reads_its_own_replica(self, tmp_path):
        binary = app_settings.bin_path
        if not binary.exists():
            pytest.skip("litestream binary not bundled")

        try:
            from litestream_vfs import loadable_path
        except ImportError:
            pytest.skip("litestream-vfs is not installed")

        extension = Path(loadable_path())
        if not extension.exists():
            pytest.skip("litestream VFS extension is not installed")

        for alias, value in (("one", "alpha"), ("two", "bravo")):
            with sqlite3.connect(tmp_path / f"{alias}.db") as conn:
                conn.execute("CREATE TABLE t (v TEXT)")
                conn.execute("INSERT INTO t VALUES (?)", (value,))

        config = tmp_path / "litestream.yml"
        config.write_text(
            "dbs:\n"
            f"  - path: {tmp_path / 'one.db'}\n"
            f"    replica:\n      url: file://{tmp_path / 'replica-one'}\n"
            f"  - path: {tmp_path / 'two.db'}\n"
            f"    replica:\n      url: file://{tmp_path / 'replica-two'}\n"
        )
        subprocess.run(
            [str(binary), "replicate", "-config", str(config), "-once"],
            check=True,
            capture_output=True,
        )

        loader_conn = sqlite3.connect(":memory:")
        loader_conn.enable_load_extension(True)
        try:
            loader_conn.load_extension(
                str(extension), entrypoint="sqlite3_litestreamvfs_init"
            )
        except TypeError:
            loader_conn.execute(
                "SELECT load_extension(?, ?)",
                [str(extension), "sqlite3_litestreamvfs_init"],
            )
        loader_conn.close()

        from django_litestream_vfs import _database_name

        for alias, value in (("one", "alpha"), ("two", "bravo")):
            name = _database_name(alias, f"file://{tmp_path}/replica-{alias}", {})
            with sqlite3.connect(name, uri=True) as conn:
                assert conn.execute("SELECT v FROM t").fetchone() == (value,)
