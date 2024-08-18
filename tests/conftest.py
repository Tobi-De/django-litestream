from __future__ import annotations

import logging

from django.conf import settings

pytest_plugins = []  # type: ignore


LITESTREAM = {
    "config_file": "litestream.yml",
}


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
        LITESTREAM=LITESTREAM,
    )
