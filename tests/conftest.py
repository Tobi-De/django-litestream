from __future__ import annotations

import logging

import pytest
from django.conf import settings

pytest_plugins = []  # type: ignore


def pytest_configure(config):
    logging.disable(logging.CRITICAL)

    settings.configure(
        ALLOWED_HOSTS=["*"],
        DEBUG=False,
        CACHES={
            "default": {
                "BACKEND": "django.core.cache.backends.dummy.DummyCache",
            }
        },
        DATABASES={
            "default": {
                "ENGINE": "django.db.backends.sqlite3",
                "NAME": "db.sqlite3",
            }
        },
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        LOGGING_CONFIG=None,
        PASSWORD_HASHERS=[
            "django.contrib.auth.hashers.MD5PasswordHasher",
        ],
        SECRET_KEY="not-a-secret",
        LITESTREAM={},
    )


@pytest.fixture
def bin_path(tmp_path):
    """A fake litestream binary so handle() doesn't raise FileNotFoundError."""
    dummy = tmp_path / "litestream"
    dummy.write_bytes(b"\x00")
    dummy.chmod(0o755)
    return dummy
