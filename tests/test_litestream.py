from __future__ import annotations

import shutil
import sqlite3
import subprocess
from unittest.mock import patch

from django.test import override_settings
from yaml import load
from yaml import Loader

from django_litestream.management.commands.litestream import (
    Command,
    generate_temp_config,
)


# def test_empty_dbs_not_allowed():
#     with override_settings(LITESTREAM={}):
#         with pytest.raises(ValueError):
#             generate_temp_config()


def test_generate_temp_config_user_defined_with_replica():
    """Test that user-defined db with replica is used as-is."""
    litestream_config = {
        "dbs": [
            {
                "path": "db.sqlite3",
                "replica": {
                    "type": "s3",
                    "bucket": "my-bucket",
                    "path": "custom.sqlite3",
                },
            }
        ],
    }
    with override_settings(LITESTREAM=litestream_config):
        with generate_temp_config() as config_path:
            with open(config_path) as f:
                config = load(f, Loader=Loader)

            assert len(config["dbs"]) == 1
            assert config["dbs"][0]["path"] == "db.sqlite3"
            assert config["dbs"][0]["replica"]["bucket"] == "my-bucket"
            assert config["dbs"][0]["replica"]["path"] == "custom.sqlite3"


def test_generate_temp_config_user_defined_auto_replica():
    """Test that replica is auto-generated when not specified by user."""
    litestream_config = {
        "dbs": [
            {
                "path": "db.sqlite3",
            }
        ],
    }
    with override_settings(LITESTREAM=litestream_config):
        with generate_temp_config() as config_path:
            with open(config_path) as f:
                config = load(f, Loader=Loader)

            assert len(config["dbs"]) == 1
            assert config["dbs"][0]["path"] == "db.sqlite3"
            # Replica should be auto-generated
            assert "replica" in config["dbs"][0]
            assert config["dbs"][0]["replica"]["type"] == "s3"
            assert config["dbs"][0]["replica"]["bucket"] == "$LITESTREAM_REPLICA_BUCKET"
            assert config["dbs"][0]["replica"]["path"] == "db.sqlite3"
            # Global credentials should be added
            assert config["access-key-id"] == "$LITESTREAM_ACCESS_KEY_ID"
            assert config["secret-access-key"] == "$LITESTREAM_SECRET_ACCESS_KEY"


def test_generate_temp_config_with_path_prefix():
    """Test that path_prefix is applied to auto-generated replica paths."""
    litestream_config = {
        "path_prefix": "myproject",
        "dbs": [
            {
                "path": "db.sqlite3",
            }
        ],
    }
    with override_settings(LITESTREAM=litestream_config):
        with generate_temp_config() as config_path:
            with open(config_path) as f:
                config = load(f, Loader=Loader)

            assert config["dbs"][0]["replica"]["path"] == "myproject/db.sqlite3"


def test_generate_temp_config_multiple_dbs():
    """Test multiple databases can be configured."""
    litestream_config = {
        "dbs": [
            {"path": "db.sqlite3"},
            {
                "path": "other.sqlite3",
                "replica": {
                    "type": "s3",
                    "bucket": "other-bucket",
                    "path": "other.sqlite3",
                },
            },
        ],
    }

    # Add second database to Django DATABASES
    with override_settings(
        LITESTREAM=litestream_config,
        DATABASES={
            "default": {
                "ENGINE": "django.db.backends.sqlite3",
                "NAME": "db.sqlite3",
            },
            "other": {
                "ENGINE": "django.db.backends.sqlite3",
                "NAME": "other.sqlite3",
            },
        },
    ):
        with generate_temp_config() as config_path:
            with open(config_path) as f:
                config = load(f, Loader=Loader)

            assert len(config["dbs"]) == 2
            # First db should have auto-generated replica
            assert config["dbs"][0]["path"] == "db.sqlite3"
            assert config["dbs"][0]["replica"]["bucket"] == "$LITESTREAM_REPLICA_BUCKET"
            # Second db should use user-defined replica
            assert config["dbs"][1]["path"] == "other.sqlite3"
            assert config["dbs"][1]["replica"]["bucket"] == "other-bucket"


def test_verify(tmp_path):
    sqlite_db = tmp_path / "db.sqlite3"
    temp_config = tmp_path / "litestream.yml"

    def mock_subprocess_run(*args, **kwargs):
        shutil.copy(sqlite_db, args[0][5])
        return subprocess.CompletedProcess(args, 0)

    with (
        patch("time.sleep", side_effect=lambda _: _),
        patch("subprocess.run", side_effect=mock_subprocess_run),
    ):
        exit_code, msg = Command().verify(sqlite_db, config=temp_config)
        assert exit_code == 0


def test_verify_fails(tmp_path):
    sqlite_db = tmp_path / "db.sqlite3"
    outdated_db = tmp_path / "outdated.sqlite3"
    temp_config = tmp_path / "litestream.yml"
    with sqlite3.connect(outdated_db) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS _litestream_verification(id INTEGER PRIMARY KEY, code TEXT, created TEXT) strict;"
        )
        conn.commit()

    def mock_subprocess_run(*args, **kwargs):
        shutil.copy(outdated_db, args[0][5])
        return subprocess.CompletedProcess(args, 0)

    with (
        patch("time.sleep", side_effect=lambda _: _),
        patch("subprocess.run", side_effect=mock_subprocess_run),
    ):
        exit_code, msg = Command().verify(sqlite_db, config=temp_config)
        assert exit_code == 1
