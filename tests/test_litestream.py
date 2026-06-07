from __future__ import annotations

import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

from django.test import override_settings
from yaml import load
from yaml import Loader

from django_litestream.conf import app_settings
from django_litestream.management.commands.litestream import (
    Command,
    DAEMON_COMMANDS,
    LITESTREAM_COMMANDS,
    generate_temp_config,
)


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
            assert config["dbs"][0]["path"].endswith("db.sqlite3")
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
            assert config["dbs"][0]["path"].endswith("db.sqlite3")
            assert "replica" in config["dbs"][0]
            assert config["dbs"][0]["replica"]["type"] == "s3"
            assert config["dbs"][0]["replica"]["bucket"] == "$LITESTREAM_REPLICA_BUCKET"
            assert config["dbs"][0]["replica"]["path"] == "db.sqlite3"
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
            assert config["dbs"][0]["path"].endswith("db.sqlite3")
            assert config["dbs"][0]["replica"]["bucket"] == "$LITESTREAM_REPLICA_BUCKET"
            assert config["dbs"][1]["path"].endswith("other.sqlite3")
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


def test_daemon_commands_defined():
    """Test that all daemon control commands are properly defined."""
    expected = {"info", "list", "register", "unregister", "start", "stop"}
    assert set(DAEMON_COMMANDS.keys()) == expected

    for cmd in DAEMON_COMMANDS:
        assert "description" in DAEMON_COMMANDS[cmd]
        assert "arguments" in DAEMON_COMMANDS[cmd]
        for arg in DAEMON_COMMANDS[cmd]["arguments"]:
            assert "name" in arg


def test_parse_daemon_args_basic():
    """Test daemon args parsing with basic options."""
    cmd = Command()

    with patch.object(cmd, "stdout"):
        args = cmd.parse_daemon_args(
            "info",
            {"json": True, "timeout": 30, "socket": "/tmp/litestream.sock"},
        )
        assert args[0] == "info"
        assert "-json" in args
        assert "-timeout" in args and "30" in args
        assert "-socket" in args and "/tmp/litestream.sock" in args


def test_parse_daemon_args_with_db_path():
    """Test daemon args parsing with a db_path positional."""
    cmd = Command()

    with patch(
        "django_litestream.management.commands.litestream.settings"
    ) as mock_settings:
        mock_settings.DATABASES = {}
        with patch.object(cmd, "stdout"):
            args = cmd.parse_daemon_args(
                "register",
                {"db_path": "db.sqlite3", "replica": "s3://bucket/db.sqlite3"},
            )
            assert "register" in args
            assert "db.sqlite3" in args
            assert "-replica" in args
            assert "s3://bucket/db.sqlite3" in args


def test_parse_daemon_args_bool_flags_omitted_when_false():
    """Test that boolean flags are omitted when False."""
    cmd = Command()

    with patch.object(cmd, "stdout"):
        args = cmd.parse_daemon_args("info", {"json": False})
        assert "-json" not in args


def test_parse_daemon_args_none_omitted():
    """Test that None values are omitted from args."""
    cmd = Command()

    with patch.object(cmd, "stdout"):
        args = cmd.parse_daemon_args("info", {"socket": None})
        assert "-socket" not in args


def test_bin_path_default():
    """Test that bin_path defaults to <venv>/bin/litestream."""
    expected = Path(sys.executable).parent / "litestream"
    assert app_settings.bin_path == expected


def test_handle_missing_binary(tmp_path):
    """Test handle() raises FileNotFoundError when binary doesn't exist."""
    cmd = Command()
    with override_settings(LITESTREAM={"bin_path": str(tmp_path / "nonexistent")}):
        import pytest

        with pytest.raises(FileNotFoundError, match="Litestream binary not found"):
            cmd.handle(subcommand="config")


def test_litestream_command_coverage():
    """Test that LITESTREAM_COMMANDS includes all expected upstream commands."""
    expected = {
        "databases",
        "ltx",
        "mcp",
        "replicate",
        "restore",
        "status",
        "sync",
        "version",
        "wal",
        "reset",
    }
    assert set(LITESTREAM_COMMANDS.keys()) == expected
