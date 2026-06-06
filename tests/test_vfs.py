from __future__ import annotations

import platform
import sys
from pathlib import Path
from unittest.mock import patch

from django.test import override_settings


def test_vfs_extension_path_default_linux():
    """vfs_extension_path defaults to alongside the main binary on Linux."""
    with patch.object(platform, "system", return_value="Linux"):
        from django_litestream_vfs.conf import VfsSettings
        expected = Path(sys.executable).parent / "litestream.so"
        assert VfsSettings().vfs_extension_path == expected


def test_vfs_extension_path_default_macos():
    """vfs_extension_path defaults with .dylib on macOS."""
    with patch.object(platform, "system", return_value="Darwin"):
        from django_litestream_vfs.conf import VfsSettings
        expected = Path(sys.executable).parent / "litestream.dylib"
        assert VfsSettings().vfs_extension_path == expected


def test_vfs_extension_path_custom():
    """Custom vfs_extension_path overrides the default."""
    with override_settings(LITESTREAM={"vfs_extension_path": "/opt/vfs/litestream.so"}):
        from django_litestream_vfs.conf import VfsSettings
        assert VfsSettings().vfs_extension_path == Path("/opt/vfs/litestream.so")


def test_ensure_vfs_loaded_missing(tmp_path):
    """ensure_vfs_loaded raises when extension is missing."""
    from django_litestream_vfs import loader

    loader._vfs_loaded = False

    fake_path = str(tmp_path / "nonexistent.so")
    with override_settings(LITESTREAM={"vfs_extension_path": fake_path}):
        import pytest
        with pytest.raises(FileNotFoundError, match="Litestream VFS extension not found"):
            loader.ensure_vfs_loaded()


def test_get_vfs_databases():
    """get_vfs_databases generates correct Django configs."""
    from django_litestream_vfs import get_vfs_databases

    vfs_config = {
        "prod_replica": "s3://mybucket/db.sqlite3",
    }
    with override_settings(LITESTREAM={"vfs": vfs_config}):
        dbs = get_vfs_databases()
        assert "prod_replica" in dbs
        assert dbs["prod_replica"]["ENGINE"] == "django_litestream_vfs.backends.sqlite_vfs"
        assert dbs["prod_replica"]["OPTIONS"]["uri"] is True
        assert dbs["prod_replica"]["OPTIONS"]["litestream_replica_url"] == "s3://mybucket/db.sqlite3"


def test_get_vfs_databases_empty():
    """get_vfs_databases returns empty dict when no VFS configured."""
    from django_litestream_vfs import get_vfs_databases

    with override_settings(LITESTREAM={}):
        dbs = get_vfs_databases()
        assert dbs == {}
