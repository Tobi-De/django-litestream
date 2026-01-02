from __future__ import annotations
import platform

import datetime as dt
import secrets
import sqlite3
import subprocess
import tempfile
import time
from contextlib import contextmanager
from itertools import chain
from pathlib import Path
from typing import TYPE_CHECKING

from django.conf import settings
from django.core.management import BaseCommand
import yaml
import sys

import io
import tarfile
import urllib.request
import zipfile
from django_litestream import get_vfs_databases, get_vfs_status
from django_litestream.conf import app_settings

if TYPE_CHECKING:
    from argparse import ArgumentParser


LITESTREAM_VERSION = "0.5.5"
VFS_VERSION = "0.5.5"
UPSTREAM_REPO = "https://github.com/benbjohnson/litestream"

LITESTREAM_COMMANDS = {
    "databases": {
        "description": "List databases specified in config file",
        "arguments": [],
    },
    "ltx": {
        "description": "List available LTX files for a database",
        "arguments": [
            {
                "name": "db_path",
                "help": "Path to the SQLite database file or replica URL",
            },
            {
                "name": "-replica",
                "help": "Optional, filters by replica. Only applies when listing database LTX files.",
                "required": False,
            },
        ],
    },
    "replicate": {
        "description": "Runs a server to replicate databases",
        "arguments": [
            {
                "name": "-exec",
                "nargs": "+",
                "help": "Executes a subcommand. Litestream will exit when the child process exits. "
                "Useful for simple process management.",
                "required": False,
            },
        ],
    },
    "restore": {
        "description": "Recovers database backup from a replica",
        "arguments": [
            {
                "name": "db_path",
                "help": "Path to the SQLite database file or replica URL",
            },
            {
                "name": "-replica",
                "help": "Restore from a specific replica.Defaults to replica with latest data.",
                "required": False,
            },
            {
                "name": "-o",
                "type": Path,
                "help": "Output path of the restored database. Defaults to original DB path.",
                "required": False,
            },
            {
                "name": "-if-replica-exists",
                "action": "store_true",
                "help": "Returns exit code of 0 if no backups found.",
                "required": False,
            },
            {
                "name": "-if-db-not-exists",
                "action": "store_true",
                "help": "Returns exit code of 0 if the database already exists.",
                "required": False,
            },
            {
                "name": "-parallelism",
                "type": int,
                "help": "Determines the number of LTX files downloaded in parallel. Defaults to 8",
                "required": False,
            },
            {
                "name": "-generation",
                "help": "Restore from a specific generation. Defaults to generation with latest data",
                "required": False,
            },
            {
                "name": "-index",
                "type": int,
                "help": "Restore up to a specific LTX index (inclusive). Defaults to use the highest available index.",
                "required": False,
            },
            {
                "name": "-timestamp",
                # "type": datetime,
                "help": "Restore to a specific point-in-time. Defaults to use the latest available backup.",
                "required": False,
            },
        ],
    },
    "version": {"description": "Prints the binary version", "arguments": []},
}


class Command(BaseCommand):
    help = "Litestream is a tool for replicating SQLite databases."

    def add_arguments(self, parser: ArgumentParser) -> None:
        subcommands = parser.add_subparsers(help="subcommands", dest="subcommand")

        subcommands.add_parser(
            "config",
            help="Show the current Litestream configuration",
            description="Show the current Litestream configuration generated from Django settings",
        )

        for ls_cmd, details in LITESTREAM_COMMANDS.items():
            parser = subcommands.add_parser(
                ls_cmd,
                help=details["description"],
                description=details["description"],
            )
            for args in details["arguments"]:
                copied_args = args.copy()
                name = copied_args.pop("name")
                parser.add_argument(name, **copied_args)
            parser.add_argument(
                "-no-expand-env",
                action="store_true",
                help="Disables environment variable expansion in configuration file.",
                required=False,
            )

        verify_cmd = subcommands.add_parser(
            name="verify",
            help="Verify the integrity of backed-up databases",
            description="Verify the integrity of backed-up databases",
        )
        verify_cmd.add_argument(
            "db_path",
            help="Path to the SQLite database file or django database alias",
        )

        subcommands.add_parser(
            name="vfs-install",
            help="Download and install the Litestream VFS extension",
            description="Download and install the Litestream VFS extension for read-only replica access",
        )

        subcommands.add_parser(
            name="vfs-status",
            help="Show status of all VFS replica databases",
            description="Display replication lag, transaction IDs, and health status for VFS replicas",
        )

    def handle(self, *_, **options) -> None:
        # Check if litestream binary exists, download if not
        if not app_settings.bin_path.exists():
            self.stdout.write(
                self.style.WARNING(
                    f"Litestream binary not found at {app_settings.bin_path}. Downloading..."
                )
            )
            download_binary()

        if options["subcommand"] == "config":
            with generate_temp_config() as config:
                self.stdout.write(Path(config).read_text())
        elif options["subcommand"] == "version":
            subprocess.run([app_settings.bin_path, "version"])
        elif options["subcommand"] == "verify":
            with generate_temp_config() as config:
                exit_code, msg = self.verify(
                    _db_location_from_alias(options["db_path"]), config=config
                )
            style = self.style.ERROR if exit_code else self.style.SUCCESS
            self.stdout.write(style(msg))
            exit(exit_code)
        elif options["subcommand"] == "vfs-install":
            if app_settings.vfs_extension_path.exists():
                self.stdout.write(
                    self.style.WARNING(
                        f"VFS extension already exists at {app_settings.vfs_extension_path}"
                    )
                )
                self.stdout.write("Re-downloading...")
            try:
                download_vfs_extension()
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Successfully installed VFS extension to {app_settings.vfs_extension_path}"
                    )
                )
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f"Failed to install VFS extension: {e}")
                )
                exit(1)
        elif options["subcommand"] == "vfs-status":

            vfs_databases = get_vfs_databases()

            if not vfs_databases:
                self.stdout.write(
                    self.style.WARNING(
                        "No VFS databases configured. Add VFS replicas to LITESTREAM['vfs'] in settings."
                    )
                )
                return

            self.stdout.write(
                self.style.SUCCESS(f"Found {len(vfs_databases)} VFS database(s):\n")
            )

            for alias in vfs_databases:
                self.stdout.write(f"\n{self.style.HTTP_INFO(alias)}:")
                try:
                    status = get_vfs_status(alias)

                    self.stdout.write(f"  Replica URL: {status['replica_url']}")

                    if status['txid'] is not None:
                        self.stdout.write(f"  Transaction ID: {status['txid']}")
                    else:
                        self.stdout.write(
                            f"  Transaction ID: {self.style.WARNING('unavailable')}"
                        )

                    # Display lag with color coding
                    if status['lag_seconds'] is not None:
                        lag = status['lag_seconds']
                        if lag < 60:
                            lag_style = self.style.SUCCESS
                            lag_msg = f"{lag:.1f}s"
                        elif lag < 300:  # 5 minutes
                            lag_style = self.style.WARNING
                            lag_msg = f"{lag:.1f}s ({lag/60:.1f}m)"
                        else:
                            lag_style = self.style.ERROR
                            lag_msg = f"{lag:.1f}s ({lag/60:.1f}m)"

                        self.stdout.write(f"  Replication Lag: {lag_style(lag_msg)}")
                    else:
                        self.stdout.write(
                            f"  Replication Lag: {self.style.WARNING('unavailable')}"
                        )

                    # Overall status
                    if status['txid'] is not None and status['lag_seconds'] is not None:
                        if status['lag_seconds'] < 60:
                            self.stdout.write(f"  Status: {self.style.SUCCESS('✓ Healthy')}")
                        elif status['lag_seconds'] < 300:
                            self.stdout.write(f"  Status: {self.style.WARNING('⚠ Lagging')}")
                        else:
                            self.stdout.write(f"  Status: {self.style.ERROR('✗ Stale')}")
                    else:
                        self.stdout.write(f"  Status: {self.style.WARNING('? Unknown')}")

                except Exception as e:
                    self.stdout.write(f"  {self.style.ERROR(f'Error: {e}')}")
        elif not options["subcommand"]:
            self.print_help("manage", "litestream")
        else:
            with generate_temp_config() as config:
                options["config"] = Path(config)
                ls_args = self.parse_args(options["subcommand"], options)
                if options["verbosity"] > 2:
                    self.stdout.write(f"Options: {options}")
                if options["verbosity"] > 1:
                    self.stdout.write(f"Litestream bin: {app_settings.bin_path}")
                    self.stdout.write(f"Litestream args: {ls_args}")
                try:
                    subprocess.run([app_settings.bin_path, *ls_args], check=False)
                except KeyboardInterrupt:
                    self.stdout.write("Litestream command interrupted")

    def parse_args(self, subcommand: str, options: dict) -> list[str]:
        """This method formats the command line arguments for litestream binary."""
        positionals = []
        optionals = ["-config", str(options["config"])]

        for argument in LITESTREAM_COMMANDS[subcommand]["arguments"]:
            arg_name = argument["name"]
            dest = arg_name.strip("-").replace("-", "_")
            if dest not in options:
                continue
            value = options[dest]
            is_bool = isinstance(value, bool)
            if is_bool and not value:
                continue
            if value is None:
                continue
            if dest == "db_path":
                value = _db_location_from_alias(value)
            if isinstance(value, list):
                value = " ".join(value).strip()

            if arg_name.startswith("-"):
                if is_bool:
                    optionals.append(arg_name)
                else:
                    optionals.extend([arg_name, str(value)])
            else:
                positionals.append(str(value))
        return [subcommand, *list(chain(optionals)), *positionals]

    def verify(self, db_path: str | Path, config: str | Path) -> tuple[int, str]:
        self.stdout.write("Verifying...")
        data = secrets.token_hex(), dt.datetime.now()
        with sqlite3.connect(db_path) as db:
            cursor = db.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS _litestream_verification(id INTEGER PRIMARY KEY, code TEXT, created TEXT) strict;"""
            )
            cursor.execute(
                "INSERT INTO _litestream_verification (code, created) VALUES (?, ?)",
                data,
            )
            db.commit()

        time.sleep(10)

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_db_path = (Path(temp_dir) / db_path).with_suffix(".restored").name
            result = subprocess.run(
                [
                    app_settings.bin_path,
                    "restore",
                    "-config",
                    config,
                    "-o",
                    temp_db_path,
                    db_path,
                ],
                stdout=subprocess.PIPE,
            )
            if result.returncode != 0:
                return result.returncode, "Database restore failed"

            with sqlite3.connect(temp_db_path) as db:
                cursor = db.cursor()
                cursor.execute(
                    "SELECT code, created FROM _litestream_verification WHERE code = ? and created = ?",
                    data,
                )
                row = cursor.fetchone()

        if not row:
            return 1, "Oops! Backup data seems to be out of sync"
        return 0, "All good! Backup data is in sync"


def _db_location_from_alias(alias: str) -> str:
    db_settings = settings.DATABASES.get(alias, {})
    if db_settings.get("ENGINE") == "django.db.backends.sqlite3":
        return db_settings["NAME"]
    return alias


@contextmanager
def generate_temp_config():
    """Generate a temporary litestream config file from Django settings."""
    config = app_settings.litestream_settings()
    dbs = config.get("dbs", [])
    processed_dbs = []
    for user_db in dbs:
        path = _db_location_from_alias(user_db["path"])
        db_settings = next(
            (s for s in settings.DATABASES.values() if s["NAME"] == path), None
        )
        if not db_settings:
            continue
        if db_settings["ENGINE"] != "django.db.backends.sqlite3":
            continue
        db_conf = {"path": str(Path(path).resolve())}
        if "replica" not in user_db:
            # since we are adding replica config, add global credentials too if missing
            if "access-key-id" not in config:
                config["access-key-id"] = "$LITESTREAM_ACCESS_KEY_ID"
            if "secret-access-key" not in config:
                config["secret-access-key"] = "$LITESTREAM_SECRET_ACCESS_KEY"
            backup_path = Path(path).name
            path_prefix = app_settings.path_prefix.rstrip("/")
            backup_path = f"{path_prefix}/{backup_path}" if path_prefix else backup_path
            db_conf["replica"] = {
                "type": "s3",
                "bucket": "$LITESTREAM_REPLICA_BUCKET",
                "path": backup_path,
            }
        else:
            db_conf["replica"] = user_db["replica"]
        processed_dbs.append(db_conf)

    config["dbs"] = processed_dbs

    if not processed_dbs:
        print("No valid SQLite databases found for Litestream configuration")
        raise sys.exit(1)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
        yaml.dump(config, f, sort_keys=False)
        config_path = f.name

    try:
        yield config_path
    finally:
        Path(config_path).unlink(missing_ok=True)



def _build_litestream_download_url(basename: str, version: str) -> str:
    system = platform.system().lower()
    machine = platform.machine().lower()

    # Normalize machine architecture
    if machine in ("aarch64", "arm64"):
        arch = "arm64"
    elif machine in ("x86_64", "amd64"):
        arch = "x86_64"
    elif machine in ("armv7l", "armv7"):
        arch = "armv7"
    elif machine in ("armv6l", "armv6"):
        arch = "armv6"
    else:
        raise ValueError(f"Unsupported architecture: {machine}")

    if basename == "litestream-vfs" and arch not in ("x86_64", "arm64"):
        raise ValueError(
            f"Unsupported architecture for VFS: {machine}. "
            "VFS extension only supports x86_64 and arm64."
        )

    if basename == "litestream-vfs" and system == "windows":
        raise ValueError(f"Unsupported operating system for VFS: {system}. Windows is not supported.")

    if system not in ("linux", "darwin", "windows"):
        raise ValueError(f"Unsupported operating system: {system}")

    if system in ("darwin", "windows") and arch not in ("arm64", "x86_64"):
        raise ValueError(
            f"Unsupported {system} architecture: {arch}. "
            f"{system.title()} only supports x86_64 and arm64."
        )

    # VFS uses different naming convention
    if basename == "litestream-vfs":
        # VFS: litestream-vfs-v{version}-{system}-{amd64|arm64}.tar.gz
        vfs_arch = "amd64" if arch == "x86_64" else arch
        filename = f"{basename}-v{version}-{system}-{vfs_arch}.tar.gz"
    else:
        # Regular litestream: litestream-{version}-{system}-{arch}.{tar.gz|zip}
        platform_tag = f"{system}-{arch}"
        if system == "windows":
            filename = f"{basename}-{version}-{platform_tag}.zip"
        else:
            filename = f"{basename}-{version}-{platform_tag}.tar.gz"

    return f"{UPSTREAM_REPO}/releases/download/v{version}/{filename}"



def download_binary():
    download_url = _build_litestream_download_url("litestream", LITESTREAM_VERSION)
    system = platform.system().lower()
    
    print(f"Downloading litestream {LITESTREAM_VERSION}...")
    print(f"URL: {download_url}")

    # Download the binary
    with urllib.request.urlopen(download_url) as response:
        data = response.read()

    install_path = app_settings.bin_path
    install_path.parent.mkdir(parents=True, exist_ok=True)

    # Extract the binary from archive
    if system == "windows":
        # Windows zip file
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            # Find the litestream executable in the zip
            for member in zf.namelist():
                if member.endswith("litestream.exe") or member.endswith("litestream"):
                    with zf.open(member) as source:
                        with open(install_path, "wb") as target:
                            target.write(source.read())
                    break
    else:
        # Linux/macOS tar.gz file
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tf:
            # Find the litestream executable in the tarball
            for member in tf.getmembers():
                if member.name.endswith("litestream") and member.isfile():
                    with tf.extractfile(member) as source:
                        with open(install_path, "wb") as target:
                            target.write(source.read())
                    break

    # Make executable on Unix systems
    if system != "windows":
        install_path.chmod(0o755)

    print(f"Litestream binary installed to: {install_path}")
    return install_path


def download_vfs_extension():
    download_url = _build_litestream_download_url("litestream-vfs", VFS_VERSION)
    system = platform.system().lower()

    print(f"Downloading Litestream VFS extension {VFS_VERSION}...")
    print(f"URL: {download_url}")

    # Download the extension archive
    try:
        with urllib.request.urlopen(download_url) as response:
            data = response.read()
    except Exception as e:
        raise RuntimeError(
            f"Failed to download VFS extension from {download_url}. Error: {e}"
        ) from e

    install_path = app_settings.vfs_extension_path
    install_path.parent.mkdir(parents=True, exist_ok=True)

    # The VFS extension file is just named "litestream" not "litestream-vfs"
    extension_name = "litestream.dylib" if system == "darwin" else "litestream.so"

    try:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tf:
            # Find the VFS extension file in the tarball
            for member in tf.getmembers():
                if member.name.endswith(extension_name) and member.isfile():
                    with tf.extractfile(member) as source:
                        with open(install_path, "wb") as target:
                            target.write(source.read())
                    break
            else:
                raise RuntimeError(
                    f"Could not find {extension_name} in the downloaded archive"
                )
    except Exception as e:
        raise RuntimeError(
            f"Failed to extract VFS extension from archive. Error: {e}"
        ) from e

    # Make executable on Unix systems
    if system != "windows":
        install_path.chmod(0o755)

    print(f"Litestream VFS extension installed to: {install_path}")
    return install_path
