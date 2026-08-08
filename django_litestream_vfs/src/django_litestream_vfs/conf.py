# SPDX-FileCopyrightText: 2024-present Tobi DEGNON <tobidegnon@proton.me>
#
# SPDX-License-Identifier: MIT

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from django_litestream.conf import AppSettings


@dataclass(frozen=True)
class VfsSettings(AppSettings):
    @property
    def vfs_config(self) -> dict[str, object]:
        return self.user_settings.get("vfs", {})

    @property
    def vfs_extension_path(self) -> Path:
        custom = self.user_settings.get("vfs_extension_path")
        if custom:
            return Path(custom)
        from litestream_vfs import loadable_path

        return Path(loadable_path())


vfs_settings = VfsSettings()
