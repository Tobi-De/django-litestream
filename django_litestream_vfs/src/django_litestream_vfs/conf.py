# SPDX-FileCopyrightText: 2024-present Tobi DEGNON <tobidegnon@proton.me>
#
# SPDX-License-Identifier: MIT

from __future__ import annotations

import platform
import sys
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings


@dataclass(frozen=True)
class VfsSettings:
    @property
    def user_settings(self) -> dict[str, object]:
        return getattr(settings, "LITESTREAM", {})

    @property
    def bin_path(self) -> Path:
        return Path(
            self.user_settings.get(
                "bin_path",
                Path(sys.executable).parent / "litestream",
            )
        )

    @property
    def vfs_extension_path(self) -> Path:
        custom = self.user_settings.get("vfs_extension_path")
        if custom:
            return Path(custom)
        system = platform.system().lower()
        ext = "litestream.dylib" if system == "darwin" else "litestream.so"
        return self.bin_path.parent / ext


vfs_settings = VfsSettings()
