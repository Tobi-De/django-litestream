#!/usr/bin/env python3
"""Build platform-specific wheels for django-litestream and django-litestream-vfs.

Downloads upstream litestream releases, extracts the binary (and VFS extension),
and packages them into PEP 427 wheels using the data/scripts/ directory so that
pip installs the binary onto the user's PATH.

Usage:
    python scripts/build_binaries.py          # build both
    python scripts/build_binaries.py --bin    # only django-litestream wheels
    python scripts/build_binaries.py --vfs    # only django-litestream-vfs wheels
"""

from __future__ import annotations

import argparse
import email.message
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
    """Read LITESTREAM_VERSION from the package source."""
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
# Each entry: (upstream_archive_suffix, pep425_platform_tag, {extra_info})
# ---------------------------------------------------------------------------

LITESTREAM_TARGETS: list[tuple[str, str]] = [
    ("linux-x86_64", "manylinux2014_x86_64.musllinux_1_1_x86_64"),
    ("linux-arm64", "manylinux2014_aarch64.musllinux_1_1_aarch64"),
    ("linux-armv7", "manylinux2014_armv7l"),
    ("linux-armv6", "manylinux2014_armv6l"),
    ("darwin-arm64", "macosx_11_0_arm64"),
    ("darwin-x86_64", "macosx_10_9_x86_64"),
]

VFS_TARGETS: list[tuple[str, str]] = [
    ("linux-x86_64", "manylinux2014_x86_64.musllinux_1_1_x86_64"),
    ("linux-arm64", "manylinux2014_aarch64.musllinux_1_1_aarch64"),
    ("darwin-arm64", "macosx_11_0_arm64"),
    ("darwin-x86_64", "macosx_10_9_x86_64"),
]

# ---------------------------------------------------------------------------
# Distribution name helpers (PEP 427 – dash becomes underscore)
# ---------------------------------------------------------------------------

BIN_DIST = "django_litestream"  # the main package itself
VFS_DIST = "django_litestream_vfs"


# ---------------------------------------------------------------------------
# URL generation
# ---------------------------------------------------------------------------


def _litestream_url(system: str, arch: str) -> str:
    """URL for the main litestream binary archive."""
    return f"{UPSTREAM_REPO}/releases/download/v{VERSION}/litestream-{VERSION}-{system}-{arch}.tar.gz"


def _vfs_url(system: str, arch: str) -> str:
    """URL for the VFS extension archive.

    VFS uses an 'amd64' naming convention for x86_64.
    """
    vfs_arch = "amd64" if arch == "x86_64" else arch
    filename = f"litestream-vfs-v{VERSION}-{system}-{vfs_arch}.tar.gz"
    return f"{UPSTREAM_REPO}/releases/download/v{VERSION}/{filename}"


def _parse_target(target: str) -> tuple[str, str]:
    """Split 'linux-x86_64' into ('linux', 'x86_64')."""
    if "-" not in target:
        raise ValueError(f"Invalid target: {target}")
    system, arch = target.split("-", 1)
    return system, arch


# ---------------------------------------------------------------------------
# Archive extraction helpers
# ---------------------------------------------------------------------------


def _extract_from_tar(data: bytes, name_match: str) -> bytes:
    """Extract a file from a .tar.gz archive. Matches files whose basename
    equals name_match, preferring exact matches over partial ones."""
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
# Wheel construction
# ---------------------------------------------------------------------------


def _make_metadata_email(name: str, version: str, summary: str, license_text: str) -> str:
    """Build the METADATA file content (PEP 566, Metadata-Version 2.1)."""
    msg = email.message.EmailMessage(policy=default_policy)
    msg["Metadata-Version"] = "2.1"
    msg["Name"] = name
    msg["Version"] = version
    msg["Summary"] = summary
    msg["License"] = license_text
    msg["Requires-Python"] = ">=3.12"
    return str(msg)


def _make_wheel_metadata(platform_tag: str, generator: str = "build_binaries.py") -> str:
    """Build the WHEEL file content."""
    lines = [
        "Wheel-Version: 1.0",
        f"Generator: {generator}",
        "Root-Is-Purelib: false",
        f"Tag: py3-none-{platform_tag}",
        "",
    ]
    return "\n".join(lines)


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
    """Build a single .whl file containing a binary in data/scripts/.

    Returns the path to the created wheel.
    """
    dist_name = wheel_name.replace("-", "_")
    wheel_filename = f"{dist_name}-{version}-py3-none-{platform_tag}.whl"

    DIST_DIR.mkdir(parents=True, exist_ok=True)
    output_path = DIST_DIR / wheel_filename

    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:

        data_dir = f"{dist_name}-{version}.data"
        dist_info_dir = f"{dist_name}-{version}.dist-info"

        script_path = f"{data_dir}/scripts/{script_name}"
        info = zipfile.ZipInfo(script_path)
        if executable:
            info.external_attr = 0o100777 << 16
        zf.writestr(info, script_data)

        metadata_content = _make_metadata_email(
            dist_name, version, summary, license_text
        )
        zf.writestr(f"{dist_info_dir}/METADATA", metadata_content)

        wheel_content = _make_wheel_metadata(platform_tag)
        zf.writestr(f"{dist_info_dir}/WHEEL", wheel_content)

        record_lines = [
            f"{script_path},,",
            f"{dist_info_dir}/METADATA,,",
            f"{dist_info_dir}/WHEEL,,",
            f"{dist_info_dir}/RECORD,,",
            "",
        ]
        zf.writestr(f"{dist_info_dir}/RECORD", "\n".join(record_lines))

    return output_path


def _build_wheel_from_pure(
    pure_wheel: Path,
    platform_tag: str,
    script_name: str,
    script_data: bytes,
) -> Path:
    """Clone a pure-Python wheel, inject a binary into data/scripts/, and re-tag.

    Used for the main django-litestream package: we take the py3-none-any wheel,
    add the litestream binary, change the platform tag, and add a build number
    so pip prefers this platform-specific wheel over the pure one.
    """
    name = pure_wheel.stem
    name = name.replace("-any", f"-{platform_tag}")

    wheel_filename = f"{name}.whl"
    output_path = DIST_DIR / wheel_filename

    with (
        zipfile.ZipFile(pure_wheel, "r") as source,
        zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as dest,
    ):
        dist_info = None

        for item in source.infolist():
            data = source.read(item.filename)

            if item.filename.endswith(".dist-info/WHEEL"):
                content = data.decode("utf-8")
                content = content.replace("Root-Is-Purelib: true", "Root-Is-Purelib: false")
                tag_line = f"Tag: py3-none-{platform_tag}"
                if "Tag:" in content:
                    content = re.sub(r"Tag:.*", tag_line, content)
                else:
                    content += f"\n{tag_line}\n"
                dest.writestr(item, content.encode("utf-8"))
                continue

            if item.filename.endswith(".dist-info/RECORD"):
                continue

            dest.writestr(item, data)

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

        record_lines = []
        for item in dest.infolist():
            record_lines.append(f"{item.filename},,")

        record_lines.append(f"{dist_info_dir}/RECORD,,")
        record_lines.append("")
        zinfo = zipfile.ZipInfo(f"{dist_info_dir}/RECORD")
        dest.writestr(zinfo, "\n".join(record_lines))

    return output_path


# ---------------------------------------------------------------------------
# Main build logic
# ---------------------------------------------------------------------------


def build_litestream_wheels(pure_wheel: Path) -> list[Path]:
    """Build platform-specific django-litestream wheels with the litestream binary."""
    built = []
    for target, platform_tag in LITESTREAM_TARGETS:
        system, arch = _parse_target(target)
        url = _litestream_url(system, arch)
        print(f"  [{target}] Downloading {url} ...")
        with urllib.request.urlopen(url) as resp:
            data = resp.read()

        binary = _extract_from_tar(data, "litestream")

        print(f"  [{target}] Building wheel for {platform_tag} ...")
        wheel = _build_wheel_from_pure(
            pure_wheel,
            platform_tag,
            "litestream",
            binary,
        )
        print(f"  [{target}] -> {wheel.name}")
        built.append(wheel)
    return built


def build_vfs_wheels() -> list[Path]:
    """Build platform-specific django-litestream-vfs wheels."""
    built = []
    for target, platform_tag in VFS_TARGETS:
        system, arch = _parse_target(target)
        url = _vfs_url(system, arch)
        print(f"  [vfs:{target}] Downloading {url} ...")
        with urllib.request.urlopen(url) as resp:
            data = resp.read()

        extension_name = "litestream.dylib" if system == "darwin" else "litestream.so"
        binary = _extract_from_tar(data, extension_name)

        script_name = extension_name
        print(f"  [vfs:{target}] Building wheel for {platform_tag} ...")
        wheel = _build_wheel(
            VFS_DIST,
            VERSION,
            script_name,
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
    parser.add_argument(
        "--no-bin",
        action="store_true",
        help="Skip django-litestream platform wheels",
    )
    parser.add_argument(
        "--no-vfs",
        action="store_true",
        help="Skip django-litestream-vfs wheels",
    )
    args = parser.parse_args()

    build_bin = not args.no_bin
    build_vfs = not args.no_vfs

    print(f"django-litestream binary builder (version: {VERSION})")
    print(f"Output directory: {DIST_DIR}")
    print()

    if build_bin:
        pure_wheels = sorted(DIST_DIR.glob("django_litestream-*-py3-none-any.whl"))
        if not pure_wheels:
            print(
                "ERROR: No pure-Python wheel found in dist/. Run 'uv build' first."
            )
            sys.exit(1)
        pure_wheel = pure_wheels[-1]
        print(f"Using pure wheel: {pure_wheel.name}")
        print()
        print("=== Building django-litestream platform wheels ===")
        build_litestream_wheels(pure_wheel)
        print()

    if build_vfs:
        print("=== Building django-litestream-vfs wheels ===")
        build_vfs_wheels()
        print()

    print("Done.")


if __name__ == "__main__":
    main()
