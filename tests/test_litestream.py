from __future__ import annotations

import shutil
import sqlite3
import subprocess
import sys
import tomllib
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
    LITESTREAM_VERSION,
    _db_location_from_alias,
    generate_temp_config,
)


def test_bundled_binary_version_matches_package_version():
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    version = tomllib.loads(pyproject.read_text())["project"]["version"]
    assert LITESTREAM_VERSION == version.split(".post")[0]


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


def test_generate_temp_config_preserves_replication_tuning_keys():
    litestream_config = {
        "dbs": [{"path": "db.sqlite3"}],
        "sync-interval": "60s",
        "l0-retention": "10m",
        "l0-retention-check-interval": "5m",
        "retention": {"enabled": True},
        "shutdown-timeout": "45s",
    }
    with override_settings(LITESTREAM=litestream_config):
        with generate_temp_config() as config_path:
            with open(config_path) as f:
                config = load(f, Loader=Loader)

            assert config["sync-interval"] == "60s"
            assert isinstance(config["sync-interval"], str)
            assert config["l0-retention"] == "10m"
            assert config["l0-retention-check-interval"] == "5m"
            assert config["retention"] == {"enabled": True}
            assert isinstance(config["retention"], dict)
            assert config["shutdown-timeout"] == "45s"


def test_generate_temp_config_forwards_all_upstream_keys():
    litestream_config = {
        "dbs": [{"path": "db.sqlite3"}],
        "heartbeat-url": "https://hc.example/ping",
        "socket": {"enabled": False},
        "verify-compaction": True,
        "path_prefix": "myproject",
        "bin_path": "/opt/litestream",
        "vfs": {"replica": "s3://bucket/db.sqlite3"},
    }
    with override_settings(LITESTREAM=litestream_config):
        with generate_temp_config() as config_path:
            with open(config_path) as f:
                config = load(f, Loader=Loader)

            assert config["heartbeat-url"] == "https://hc.example/ping"
            assert config["socket"] == {"enabled": False}
            assert config["verify-compaction"] is True
            assert "path_prefix" not in config
            assert "bin_path" not in config
            assert "vfs" not in config


def test_generate_temp_config_preserves_per_db_options():
    litestream_config = {
        "dbs": [
            {
                "path": "default",
                "snapshot": {"interval": "6h", "retention": "168h"},
                "monitor-interval": "5s",
                "truncate-page-n": 1000,
            }
        ]
    }
    with override_settings(LITESTREAM=litestream_config):
        with generate_temp_config() as config_path:
            with open(config_path) as f:
                config = load(f, Loader=Loader)
            db_config = config["dbs"][0]
            assert db_config["snapshot"] == {"interval": "6h", "retention": "168h"}
            assert db_config["monitor-interval"] == "5s"
            assert db_config["truncate-page-n"] == 1000
            assert db_config["replica"]["type"] == "s3"


def test_generate_temp_config_keeps_explicit_multiple_replicas():
    replicas = [
        {"type": "s3", "bucket": "first", "path": "db.sqlite3"},
        {"type": "s3", "bucket": "second", "path": "db.sqlite3"},
    ]
    litestream_config = {"dbs": [{"path": "default", "replicas": replicas}]}
    with override_settings(LITESTREAM=litestream_config):
        with generate_temp_config() as config_path:
            with open(config_path) as f:
                config = load(f, Loader=Loader)
            db_config = config["dbs"][0]
            assert db_config["replicas"] == replicas
            assert "replica" not in db_config


def test_generate_temp_config_passes_through_directory_entries():
    litestream_config = {
        "dbs": [
            {
                "dir": "/srv/databases",
                "pattern": "*.sqlite3",
                "watch": True,
                "replica": {"type": "s3", "bucket": "dir-bucket", "path": "dbs"},
            }
        ]
    }
    with override_settings(LITESTREAM=litestream_config):
        with generate_temp_config() as config_path:
            with open(config_path) as f:
                config = load(f, Loader=Loader)
            db_config = config["dbs"][0]
            assert db_config["dir"] == "/srv/databases"
            assert db_config["pattern"] == "*.sqlite3"
            assert db_config["watch"] is True


def test_generate_temp_config_passes_through_unmanaged_paths():
    litestream_config = {
        "dbs": [{"path": "/srv/unmanaged.db", "snapshot": {"interval": "1h"}}]
    }
    with override_settings(LITESTREAM=litestream_config):
        with generate_temp_config() as config_path:
            with open(config_path) as f:
                config = load(f, Loader=Loader)
            db_config = config["dbs"][0]
            assert db_config["path"] == "/srv/unmanaged.db"
            assert db_config["snapshot"] == {"interval": "1h"}
            assert db_config["replica"]["type"] == "s3"


# Every yaml key accepted by Litestream v0.5.18's Config/ReplicaSettings.
UPSTREAM_TOP_LEVEL_OPTIONS = {
    # Config fields
    "addr": ":9090",
    "socket": {"enabled": True, "path": "/var/run/litestream.sock"},
    "levels": [{"interval": "30s"}],
    "snapshot": {"interval": "6h", "retention": "168h"},
    "validation": {"enabled": True, "interval": "1h"},
    "l0-retention": "10m",
    "l0-retention-check-interval": "5m",
    "verify-compaction": True,
    "retention": {
        "enabled": True,
        "interval": "1h",
        "min-interval": "10m",
        "max-interval": "24h",
    },
    "heartbeat-url": "https://hc.example/ping",
    "heartbeat-interval": "10s",
    "exec": "true",
    "logging": {"level": "info", "type": "text"},
    "mcp-addr": ":9091",
    "shutdown-timeout": "45s",
    "shutdown-sync-timeout": "30s",
    "shutdown-sync-interval": "1s",
    # ReplicaSettings fields (inline at top level)
    "sync-interval": "10s",
    "validation-interval": "1h",
    "max-sync-ltx-files": 3,
    "auto-recover": True,
    "access-key-id": "$LITESTREAM_ACCESS_KEY_ID",
    "secret-access-key": "$LITESTREAM_SECRET_ACCESS_KEY",
    "region": "us-east-1",
    "bucket": "my-bucket",
    "endpoint": "http://minio:9000",
    "force-path-style": True,
    "sign-payload": False,
    "sign-accept-encoding": False,
    "require-content-md5": True,
    "put-object-content-md5": True,
    "skip-verify": True,
    "storage-class": "STANDARD",
    "part-size": "5MB",
    "concurrency": 4,
    "sse-customer-algorithm": "AES256",
    "sse-customer-key": "customer-key",
    "sse-customer-key-path": "/tmp/customer.key",
    "sse-kms-key-id": "kms-key-id",
    "account-name": "account",
    "account-key": "account-key",
    "sas-token": "sas-token",
    "host": "sftp.example.com",
    "user": "sftp-user",
    "password": "sftp-password",
    "key-path": "/tmp/id_ed25519",
    "concurrent-writes": True,
    "host-key": "ssh-ed25519 AAAA",
    "webdav-url": "https://dav.example.com",
    "webdav-username": "webdav-user",
    "webdav-password": "webdav-password",
    "jwt": "nats-jwt",
    "seed": "nats-seed",
    "creds": "/tmp/nats.creds",
    "nkey": "nats-nkey",
    "username": "nats-user",
    "token": "nats-token",
    "tls": True,
    "root-cas": "/tmp/root-ca.pem",
    "client-cert": "/tmp/client.pem",
    "client-key": "/tmp/client.key",
    "max-reconnects": 5,
    "reconnect-wait": "1s",
    "timeout": "10s",
    "identities": ["/tmp/identity"],
    "recipients": ["age1example"],
    "age": True,
}

# Every yaml key accepted by Litestream v0.5.18's DBConfig.
UPSTREAM_DB_OPTIONS = {
    "pattern": "*.sqlite3",
    "recursive": True,
    "watch": True,
    "snapshot": {"interval": "6h", "retention": "168h"},
    "meta-path": "/tmp/meta",
    "meta-dir": "/tmp/meta-dir",
    "monitor-interval": "5s",
    "checkpoint-interval": "1m",
    "busy-timeout": "5s",
    "min-checkpoint-page-count": 10,
    "truncate-page-n": 100,
    "max-sync-wal-bytes": 4096,
    "restore-if-db-not-exists": True,
    "replica": {"type": "s3", "bucket": "db-bucket", "path": "db.sqlite3"},
    "replicas": [
        {"type": "s3", "bucket": "first", "path": "db.sqlite3"},
        {"type": "s3", "bucket": "second", "path": "db.sqlite3"},
    ],
}

WRAPPER_ONLY_OPTIONS = {
    "path_prefix": "myproject",
    "bin_path": "/opt/litestream",
    "vfs": {"replica_name": "s3://bucket/db.sqlite3"},
    "vfs_extension_path": "/tmp/litestream-vfs.so",
}


@pytest.mark.parametrize("key,value", UPSTREAM_TOP_LEVEL_OPTIONS.items())
def test_generate_temp_config_forwards_every_upstream_top_level_option(key, value):
    litestream_config = {"dbs": [{"path": "db.sqlite3"}], key: value}
    with override_settings(LITESTREAM=litestream_config):
        with generate_temp_config() as config_path:
            with open(config_path) as f:
                config = load(f, Loader=Loader)
            assert config[key] == value
            assert config["dbs"][0]["path"].endswith("db.sqlite3")


@pytest.mark.parametrize("key,value", WRAPPER_ONLY_OPTIONS.items())
def test_generate_temp_config_excludes_every_wrapper_only_option(key, value):
    litestream_config = {"dbs": [{"path": "db.sqlite3"}], key: value}
    with override_settings(LITESTREAM=litestream_config):
        with generate_temp_config() as config_path:
            with open(config_path) as f:
                config = load(f, Loader=Loader)
            assert key not in config


@pytest.mark.parametrize("key,value", UPSTREAM_DB_OPTIONS.items())
def test_generate_temp_config_preserves_every_upstream_db_option(key, value):
    litestream_config = {"dbs": [{"path": "default", key: value}]}
    with override_settings(LITESTREAM=litestream_config):
        with generate_temp_config() as config_path:
            with open(config_path) as f:
                config = load(f, Loader=Loader)
            assert config["dbs"][0][key] == value


def test_generate_temp_config_forwards_unknown_keys():
    litestream_config = {
        "future-top-level-option": {"nested": 1},
        "dbs": [{"path": "default", "future-db-option": ["a", 2]}],
    }
    with override_settings(LITESTREAM=litestream_config):
        with generate_temp_config() as config_path:
            with open(config_path) as f:
                config = load(f, Loader=Loader)
            assert config["future-top-level-option"] == {"nested": 1}
            assert config["dbs"][0]["future-db-option"] == ["a", 2]


def test_generate_temp_config_does_not_inject_credentials_with_explicit_replica():
    replica = {"type": "s3", "bucket": "my-bucket", "path": "db.sqlite3"}
    litestream_config = {"dbs": [{"path": "default", "replica": replica}]}
    with override_settings(LITESTREAM=litestream_config):
        with generate_temp_config() as config_path:
            with open(config_path) as f:
                config = load(f, Loader=Loader)
            assert config["dbs"][0]["replica"] == replica
            assert "access-key-id" not in config
            assert "secret-access-key" not in config


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
