#!/usr/bin/env python3
"""Build platform-specific wheels for django-litestream and django-litestream-vfs.

Downloads upstream litestream releases, extracts the binary (and VFS extension),
and packages them into PEP 427 wheels using the data/scripts/ directory so that
pip installs the binary onto the user's PATH.

Usage:
    python scripts/build_binaries.py          # build both
    python scripts/build_binaries.py --no-bin # only VFS
    python scripts/build_binaries.py --no-vfs # only main
"""

from __future__ import annotations

import argparse
import base64
import email.message
import hashlib
import io
import re
import sys
import tarfile
import urllib.request
import zipfile
from email.policy import default as default_policy
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DIST_DIR = REPO_ROOT / "dist"


def _read_litestream_version() -> str:
    source = REPO_ROOT / "src" / "django_litestream" / "management" / "commands" / "litestream.py"
    content = source.read_text()
    match = re.search(r'^LITESTREAM_VERSION\s*=\s*"([^"]+)"', content, re.MULTILINE)
    if not match:
        raise RuntimeError(f"Could not find LITESTREAM_VERSION in {source}")
    return match.group(1)


UPSTREAM_REPO = "https://github.com/benbjohnson/litestream"
VERSION = _read_litestream_version()

# ---------------------------------------------------------------------------
# Platform target definitions
# ---------------------------------------------------------------------------

LITESTREAM_TARGETS: list[tuple[str, str]] = [
    ("linux-x86_64", "manylinux2014_x86_64.musllinux_1_1_x86_64"),
    ("linux-arm64", "manylinux2014_aarch64.musllinux_1_1_aarch64"),
    ("darwin-arm64", "macosx_11_0_arm64"),
    ("darwin-x86_64", "macosx_10_9_x86_64"),
]

VFS_TARGETS: list[tuple[str, str]] = [
    ("linux-x86_64", "manylinux2014_x86_64.musllinux_1_1_x86_64"),
    ("linux-arm64", "manylinux2014_aarch64.musllinux_1_1_aarch64"),
    ("darwin-arm64", "macosx_11_0_arm64"),
    ("darwin-x86_64", "macosx_10_9_x86_64"),
]

VFS_DIST = "django_litestream_vfs"


# ---------------------------------------------------------------------------
# URL generation
# ---------------------------------------------------------------------------


def _litestream_url(system: str, arch: str) -> str:
    return f"{UPSTREAM_REPO}/releases/download/v{VERSION}/litestream-{VERSION}-{system}-{arch}.tar.gz"


def _vfs_url(system: str, arch: str) -> str:
    vfs_arch = "amd64" if arch == "x86_64" else arch
    return f"{UPSTREAM_REPO}/releases/download/v{VERSION}/litestream-vfs-v{VERSION}-{system}-{vfs_arch}.tar.gz"


def _parse_target(target: str) -> tuple[str, str]:
    system, arch = target.split("-", 1)
    return system, arch


# ---------------------------------------------------------------------------
# Archive extraction
# ---------------------------------------------------------------------------


def _extract_from_tar(data: bytes, name_match: str) -> bytes:
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tf:
        candidates = []
        for member in tf.getmembers():
            if member.isfile() and member.name.split("/")[-1] == name_match:
                candidates.append(member)

        if not candidates:
            raise RuntimeError(
                f"Could not find file named '{name_match}' in archive"
            )

        member = candidates[0]
        extracted = tf.extractfile(member)
        if extracted is None:
            raise RuntimeError(f"Could not extract {member.name}")
        return extracted.read()


# ---------------------------------------------------------------------------
# RECORD helpers
# ---------------------------------------------------------------------------


def _record_entry(filename: str, data: bytes) -> str:
    digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
    return f"{filename},sha256={digest},{len(data)}"


# ---------------------------------------------------------------------------
# Wheel metadata
# ---------------------------------------------------------------------------


def _make_metadata(name: str, version: str, summary: str, license_text: str) -> str:
    msg = email.message.EmailMessage(policy=default_policy)
    msg["Metadata-Version"] = "2.1"
    msg["Name"] = name
    msg["Version"] = version
    msg["Summary"] = summary
    msg["License"] = license_text
    msg["Requires-Python"] = ">=3.12"
    return str(msg)


def _make_wheel_metadata(platform_tag: str) -> str:
    return "\n".join([
        "Wheel-Version: 1.0",
        "Generator: build_binaries.py",
        "Root-Is-Purelib: false",
        f"Tag: py3-none-{platform_tag}",
        "",
    ])


# ---------------------------------------------------------------------------
# Standalone wheel builder (for VFS package)
# ---------------------------------------------------------------------------


def _build_wheel(
    wheel_name: str,
    version: str,
    script_name: str,
    script_data: bytes,
    platform_tag: str,
    summary: str,
    license_text: str,
    executable: bool = True,
) -> Path:
    dist_name = wheel_name.replace("-", "_")
    wheel_filename = f"{dist_name}-{version}-py3-none-{platform_tag}.whl"

    DIST_DIR.mkdir(parents=True, exist_ok=True)
    output_path = DIST_DIR / wheel_filename

    data_dir = f"{dist_name}-{version}.data"
    dist_info_dir = f"{dist_name}-{version}.dist-info"
    script_path = f"{data_dir}/scripts/{script_name}"

    metadata_bytes = _make_metadata(dist_name, version, summary, license_text).encode()
    wheel_bytes = _make_wheel_metadata(platform_tag).encode()

    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        info = zipfile.ZipInfo(script_path)
        if executable:
            info.external_attr = 0o100777 << 16
        zf.writestr(info, script_data)

        zf.writestr(f"{dist_info_dir}/METADATA", metadata_bytes)
        zf.writestr(f"{dist_info_dir}/WHEEL", wheel_bytes)

        record_body = "\n".join([
            _record_entry(script_path, script_data),
            _record_entry(f"{dist_info_dir}/METADATA", metadata_bytes),
            _record_entry(f"{dist_info_dir}/WHEEL", wheel_bytes),
            f"{dist_info_dir}/RECORD,,",
            "",
        ])
        zf.writestr(f"{dist_info_dir}/RECORD", record_body)

    return output_path


# ---------------------------------------------------------------------------
# Wheel-from-pure builder (clones pure wheel, injects binary, re-tags)
# ---------------------------------------------------------------------------


def _build_wheel_from_pure(
    pure_wheel: Path,
    platform_tag: str,
    script_name: str,
    script_data: bytes,
) -> Path:
    name = pure_wheel.stem
    name = name.replace("-any", f"-{platform_tag}")
    wheel_filename = f"{name}.whl"
    output_path = DIST_DIR / wheel_filename

    records: list[tuple[str, bytes]] = []
    dist_info = None

    with (
        zipfile.ZipFile(pure_wheel, "r") as source,
        zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as dest,
    ):
        for item in source.infolist():
            if item.filename.endswith(".dist-info/RECORD"):
                continue

            data = source.read(item.filename)

            if item.filename.endswith(".dist-info/WHEEL"):
                content = data.decode("utf-8")
                content = content.replace("Root-Is-Purelib: true", "Root-Is-Purelib: false")
                tag_line = f"Tag: py3-none-{platform_tag}"
                if "Tag:" in content:
                    content = re.sub(r"Tag:.*", tag_line, content)
                else:
                    content += f"\n{tag_line}\n"
                data = content.encode("utf-8")

            dest.writestr(item, data)
            records.append((item.filename, data))

            if ".dist-info/" in item.filename and dist_info is None:
                dist_info = item.filename[: item.filename.index(".dist-info/") + len(".dist-info")]

        if dist_info is None:
            raise RuntimeError("Could not determine .dist-info directory from pure wheel")

        dist_prefix = dist_info.rsplit(".dist-info", 1)[0]
        data_dir = f"{dist_prefix}.data"
        dist_info_dir = dist_info

        script_path = f"{data_dir}/scripts/{script_name}"
        info = zipfile.ZipInfo(script_path)
        info.external_attr = 0o100777 << 16
        dest.writestr(info, script_data)
        records.append((script_path, script_data))

        record_body = "\n".join(
            _record_entry(filename, filedata)
            for filename, filedata in records
        )
        record_body += f"\n{dist_info_dir}/RECORD,,\n"

        zinfo = zipfile.ZipInfo(f"{dist_info_dir}/RECORD")
        dest.writestr(zinfo, record_body)

    return output_path


# ---------------------------------------------------------------------------
# Main build entry points
# ---------------------------------------------------------------------------


def build_litestream_wheels(pure_wheel: Path) -> list[Path]:
    built = []
    for target, platform_tag in LITESTREAM_TARGETS:
        system, arch = _parse_target(target)
        url = _litestream_url(system, arch)
        print(f"  [{target}] Downloading {url} ...")
        with urllib.request.urlopen(url) as resp:
            data = resp.read()

        binary = _extract_from_tar(data, "litestream")

        print(f"  [{target}] Building wheel for {platform_tag} ...")
        wheel = _build_wheel_from_pure(pure_wheel, platform_tag, "litestream", binary)
        print(f"  [{target}] -> {wheel.name}")
        built.append(wheel)
    return built


def build_vfs_wheels() -> list[Path]:
    built = []
    for target, platform_tag in VFS_TARGETS:
        system, arch = _parse_target(target)
        url = _vfs_url(system, arch)
        print(f"  [vfs:{target}] Downloading {url} ...")
        with urllib.request.urlopen(url) as resp:
            data = resp.read()

        extension_name = "litestream.dylib" if system == "darwin" else "litestream.so"
        binary = _extract_from_tar(data, extension_name)

        print(f"  [vfs:{target}] Building wheel for {platform_tag} ...")
        wheel = _build_wheel(
            VFS_DIST,
            VERSION,
            extension_name,
            binary,
            platform_tag,
            summary="Litestream VFS extension for read-only replica access",
            license_text="Apache-2.0",
        )
        print(f"  [vfs:{target}] -> {wheel.name}")
        built.append(wheel)
    return built


def main() -> None:
    parser = argparse.ArgumentParser(description="Build platform-specific binary wheels")
    parser.add_argument("--no-bin", action="store_true", help="Skip django-litestream platform wheels")
    parser.add_argument("--no-vfs", action="store_true", help="Skip django-litestream-vfs wheels")
    args = parser.parse_args()

    print(f"django-litestream binary builder (version: {VERSION})")
    print(f"Output directory: {DIST_DIR}")
    print()

    if not args.no_bin:
        pure_wheels = sorted(DIST_DIR.glob("django_litestream-*-py3-none-any.whl"))
        if not pure_wheels:
            print("ERROR: No pure-Python wheel found in dist/. Run 'uv build' first.")
            sys.exit(1)
        pure_wheel = pure_wheels[-1]
        print(f"Using pure wheel: {pure_wheel.name}")
        print()
        print("=== Building django-litestream platform wheels ===")
        build_litestream_wheels(pure_wheel)
        print()

    if not args.no_vfs:
        print("=== Building django-litestream-vfs wheels ===")
        build_vfs_wheels()
        print()

    print("Done.")


if __name__ == "__main__":
    main()
