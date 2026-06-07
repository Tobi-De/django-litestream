from __future__ import annotations

import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from django.test import override_settings
from yaml import load
from yaml import Loader

from django_litestream.conf import app_settings
from django_litestream.management.commands.litestream import (
    Command,
    DAEMON_COMMANDS,
    LITESTREAM_COMMANDS,
    _db_location_from_alias,
    generate_temp_config,
)


# ---------------------------------------------------------------------------
# Config generation
# ---------------------------------------------------------------------------


def test_generate_temp_config_user_defined_with_replica():
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
    litestream_config = {"dbs": [{"path": "db.sqlite3"}]}
    with override_settings(LITESTREAM=litestream_config):
        with generate_temp_config() as config_path:
            with open(config_path) as f:
                config = load(f, Loader=Loader)

            assert len(config["dbs"]) == 1
            assert config["dbs"][0]["path"].endswith("db.sqlite3")
            assert config["dbs"][0]["replica"]["type"] == "s3"
            assert config["dbs"][0]["replica"]["bucket"] == "$LITESTREAM_REPLICA_BUCKET"
            assert config["access-key-id"] == "$LITESTREAM_ACCESS_KEY_ID"
            assert config["secret-access-key"] == "$LITESTREAM_SECRET_ACCESS_KEY"


def test_generate_temp_config_with_path_prefix():
    litestream_config = {"path_prefix": "myproject", "dbs": [{"path": "db.sqlite3"}]}
    with override_settings(LITESTREAM=litestream_config):
        with generate_temp_config() as config_path:
            with open(config_path) as f:
                config = load(f, Loader=Loader)
            assert config["dbs"][0]["replica"]["path"] == "myproject/db.sqlite3"


def test_generate_temp_config_multiple_dbs():
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
            "default": {"ENGINE": "django.db.backends.sqlite3", "NAME": "db.sqlite3"},
            "other": {"ENGINE": "django.db.backends.sqlite3", "NAME": "other.sqlite3"},
        },
    ):
        with generate_temp_config() as config_path:
            with open(config_path) as f:
                config = load(f, Loader=Loader)
            assert len(config["dbs"]) == 2


def test_generate_temp_config_skips_non_sqlite():
    litestream_config = {"dbs": [{"path": "default"}]}
    with override_settings(
        LITESTREAM=litestream_config,
        DATABASES={
            "default": {"ENGINE": "django.db.backends.postgresql", "NAME": "mydb"}
        },
    ):
        with pytest.raises(SystemExit):
            generate_temp_config().__enter__()


def test_generate_temp_config_preserves_user_global_keys():
    litestream_config = {
        "addr": ":9090",
        "logging": "debug",
        "dbs": [{"path": "db.sqlite3"}],
    }
    with override_settings(LITESTREAM=litestream_config):
        with generate_temp_config() as config_path:
            with open(config_path) as f:
                config = load(f, Loader=Loader)
            assert config["addr"] == ":9090"
            assert config["logging"] == "debug"


# ---------------------------------------------------------------------------
# Verify command
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# CLI: parse_args (config-based commands)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("subcommand", sorted(LITESTREAM_COMMANDS))
def test_parse_args_no_extra_options(subcommand):
    """Every config-based command produces a valid cli with just -config."""
    cmd = Command()
    with patch.object(cmd, "stdout"):
        args = cmd.parse_args(subcommand, {"config": Path("/tmp/cfg.yml")})
    assert args[0] == subcommand
    assert "-config" in args


@pytest.mark.parametrize(
    "subcommand,extra_options,expected_flags",
    [
        ("databases", {}, []),
        ("ltx", {"db_path": "/tmp/db.sqlite3"}, ["/tmp/db.sqlite3"]),
        ("ltx", {"replica": "s3"}, ["-replica", "s3"]),
        ("ltx", {"level": 2}, ["-level", "2"]),
        ("replicate", {"exec": ["gunicorn", "app"]}, ["-exec", "gunicorn app"]),
        ("replicate", {"once": True}, ["-once"]),
        ("replicate", {"force_snapshot": True}, ["-force-snapshot"]),
        ("replicate", {"enforce_retention": True}, ["-enforce-retention"]),
        (
            "replicate",
            {"restore_if_db_not_exists": True},
            ["-restore-if-db-not-exists"],
        ),
        ("restore", {"db_path": "/tmp/db.sqlite3"}, ["/tmp/db.sqlite3"]),
        ("restore", {"o": Path("/tmp/out.db")}, ["-o", "/tmp/out.db"]),
        ("restore", {"if_replica_exists": True}, ["-if-replica-exists"]),
        ("restore", {"if_db_not_exists": True}, ["-if-db-not-exists"]),
        ("restore", {"parallelism": 16}, ["-parallelism", "16"]),
        (
            "restore",
            {"timestamp": "2025-01-01T00:00:00Z"},
            ["-timestamp", "2025-01-01T00:00:00Z"],
        ),
        ("restore", {"f": True}, ["-f"]),
        ("status", {"db_path": "/tmp/db.sqlite3"}, ["/tmp/db.sqlite3"]),
        ("sync", {"db_path": "/tmp/db.sqlite3"}, ["/tmp/db.sqlite3"]),
        (
            "wal",
            {"db_path": "/tmp/db.sqlite3", "replica": "s3"},
            ["-replica", "s3", "/tmp/db.sqlite3"],
        ),
        ("wal", {"generation": "abc123"}, ["-generation", "abc123"]),
        ("reset", {"db_path": "/tmp/db.sqlite3"}, ["/tmp/db.sqlite3"]),
        ("reset", {"dry_run": True}, ["-dry-run"]),
    ],
)
def test_parse_args_parametrized(subcommand, extra_options, expected_flags):
    cmd = Command()
    with patch.object(cmd, "stdout"):
        args = cmd.parse_args(
            subcommand, {"config": Path("/tmp/cfg.yml"), **extra_options}
        )
    for flag in expected_flags:
        assert flag in args, f"Expected {flag!r} in {args}"


def test_parse_args_bool_false_omitted():
    cmd = Command()
    with patch.object(cmd, "stdout"):
        args = cmd.parse_args(
            "replicate", {"config": Path("/tmp/cfg.yml"), "once": False}
        )
    assert "-once" not in args


def test_parse_args_none_omitted():
    cmd = Command()
    with patch.object(cmd, "stdout"):
        args = cmd.parse_args("ltx", {"config": Path("/tmp/cfg.yml"), "replica": None})
    assert "-replica" not in args


def test_parse_args_db_alias_resolution():
    cmd = Command()
    with patch(
        "django_litestream.management.commands.litestream.settings"
    ) as mock_conf:
        mock_conf.DATABASES = {
            "default": {
                "ENGINE": "django.db.backends.sqlite3",
                "NAME": "/path/to/db.sqlite3",
            },
        }
        with patch.object(cmd, "stdout"):
            args = cmd.parse_args(
                "sync", {"config": Path("/tmp/cfg.yml"), "db_path": "default"}
            )
    assert "/path/to/db.sqlite3" in args


# ---------------------------------------------------------------------------
# CLI: parse_daemon_args (IPC commands)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("subcommand", sorted(DAEMON_COMMANDS))
def test_daemon_args_basic(subcommand):
    cmd = Command()
    with patch.object(cmd, "stdout"):
        args = cmd.parse_daemon_args(subcommand, {})
    assert args[0] == subcommand


@pytest.mark.parametrize(
    "subcommand,opts,expected_flags",
    [
        (
            "info",
            {"json": True, "timeout": 30, "socket": "/tmp/sock"},
            ["-json", "-timeout", "30", "-socket", "/tmp/sock"],
        ),
        ("list", {"json": True}, ["-json"]),
        (
            "register",
            {"db_path": "default", "replica": "s3://b/db"},
            ["default", "-replica", "s3://b/db"],
        ),
        (
            "unregister",
            {"db_path": "default", "dry_run": True},
            ["default", "-dry-run"],
        ),
        ("start", {"db_path": "default"}, ["default"]),
        ("stop", {"db_path": "default", "timeout": 60}, ["default", "-timeout", "60"]),
    ],
)
def test_daemon_args_parametrized(subcommand, opts, expected_flags):
    cmd = Command()
    with patch(
        "django_litestream.management.commands.litestream.settings"
    ) as mock_conf:
        mock_conf.DATABASES = {}
        with patch.object(cmd, "stdout"):
            args = cmd.parse_daemon_args(subcommand, opts)
    for flag in expected_flags:
        assert flag in args, f"Expected {flag!r} in {args}"


# ---------------------------------------------------------------------------
# CLI: handle dispatch
# ---------------------------------------------------------------------------


def test_handle_binary_missing(tmp_path):
    cmd = Command()
    with override_settings(LITESTREAM={"bin_path": str(tmp_path / "nonexistent")}):
        with pytest.raises(FileNotFoundError, match="Litestream binary not found"):
            cmd.handle(subcommand="config")


def test_handle_version_calls_subprocess(bin_path):
    cmd = Command()
    with override_settings(LITESTREAM={"bin_path": str(bin_path)}):
        with patch.object(subprocess, "run") as mock_run:
            with patch.object(cmd, "stdout"):
                cmd.handle(subcommand="version", verbosity=1)
    mock_run.assert_called_once()
    assert str(mock_run.call_args[0][0][0]) == str(bin_path)


def test_handle_config_reads_config(bin_path):
    litestream_config = {"bin_path": str(bin_path), "dbs": [{"path": "db.sqlite3"}]}
    with override_settings(LITESTREAM=litestream_config):
        cmd = Command()
        with patch.object(cmd, "stdout"):
            cmd.handle(subcommand="config")


def test_handle_no_subcommand_shows_help(bin_path):
    cmd = Command()
    with override_settings(LITESTREAM={"bin_path": str(bin_path)}):
        with patch.object(cmd, "stdout"):
            with patch.object(cmd, "print_help") as mock_help:
                cmd.handle(subcommand=None, verbosity=1)
    mock_help.assert_called_once()


def test_handle_daemon_command(bin_path):
    cmd = Command()
    with override_settings(LITESTREAM={"bin_path": str(bin_path)}):
        with patch.object(subprocess, "run") as mock_run:
            with patch.object(cmd, "stdout"):
                cmd.handle(subcommand="info", verbosity=1)
    mock_run.assert_called_once()


def test_handle_config_based_command(bin_path):
    litestream_config = {"bin_path": str(bin_path), "dbs": [{"path": "db.sqlite3"}]}
    with override_settings(LITESTREAM=litestream_config):
        cmd = Command()
        with patch.object(subprocess, "run") as mock_run:
            with patch.object(cmd, "stdout"):
                cmd.handle(subcommand="databases", verbosity=1)
    mock_run.assert_called_once()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def test_db_location_from_alias_sqlite():
    with patch(
        "django_litestream.management.commands.litestream.settings"
    ) as mock_conf:
        mock_conf.DATABASES = {
            "default": {
                "ENGINE": "django.db.backends.sqlite3",
                "NAME": "/path/to/db.sqlite3",
            },
        }
        assert _db_location_from_alias("default") == "/path/to/db.sqlite3"


def test_db_location_from_alias_non_sqlite():
    with patch(
        "django_litestream.management.commands.litestream.settings"
    ) as mock_conf:
        mock_conf.DATABASES = {
            "default": {"ENGINE": "django.db.backends.postgresql", "NAME": "mydb"},
        }
        assert _db_location_from_alias("default") == "default"


def test_db_location_from_alias_unknown():
    with patch(
        "django_litestream.management.commands.litestream.settings"
    ) as mock_conf:
        mock_conf.DATABASES = {}
        assert _db_location_from_alias("unknown") == "unknown"


# ---------------------------------------------------------------------------
# Structural / regression
# ---------------------------------------------------------------------------


def test_bin_path_default():
    expected = Path(sys.executable).parent / "litestream"
    assert app_settings.bin_path == expected


def test_litestream_command_coverage():
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


def test_daemon_command_coverage():
    expected = {"info", "list", "register", "unregister", "start", "stop"}
    assert set(DAEMON_COMMANDS.keys()) == expected


def test_add_arguments_registers_all_commands():
    from argparse import ArgumentParser

    cmd = Command()
    parser = ArgumentParser()
    cmd.add_arguments(parser)
    registered = set()
    for action in parser._actions:
        if hasattr(action, "choices") and action.choices:
            registered = set(action.choices.keys())
            break

    for name in {**LITESTREAM_COMMANDS, **DAEMON_COMMANDS}:
        assert name in registered, f"{name} not registered as subcommand"
    assert "config" in registered
    assert "verify" in registered
    # vfs-install is removed
    assert "vfs-install" not in registered
