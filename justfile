set dotenv-load

# List all available commands
_default:
    @just --list --unsorted

@install:
    uv sync

@test:
    uv run --extra vfs pytest

@fmt:
    just --fmt --unstable
    uvx prek run -a

# Build platform-specific binary wheels (run 'uv build' first)
build-bin:
    uv build && python scripts/build_binaries.py

@dj *ARGS:
    cd demo && uv run python manage.py {{ ARGS }}

@run-demo:
    cd demo && uv run python manage.py runserver

logchanges *ARGS:
    uvx git-cliff --output CHANGELOG.md {{ ARGS }}

# Serve documentation with auto-reload
@docs-serve:
    uv run --group docs sphinx-autobuild docs docs/_build/html  --port 8002 --watch docs --open-browser

# Bump project version and update changelog
bumpver VERSION:
    #!/usr/bin/env bash
    set -euo pipefail
    uvx bump-my-version bump {{ VERSION }}
    just logchanges
    [ -z "$(git status --porcelain)" ] && { echo "No changes to commit."; git push && git push --tags; exit 0; }
    version="$(uvx bump-my-version show current_version)"
    git add -A
    git commit -m "Generate changelog for version ${version}"
    git tag -f "v${version}"
    git push && git push --tags

# Bump post-release version (0.5.11 → 0.5.11.post1)
# Use for wrapper-only fixes when litestream upstream hasn't changed.
# Does NOT bump VFS package (VFS version stays locked to upstream litestream).
bump-post:
    #!/usr/bin/env bash
    set -euo pipefail
    uvx bump-my-version bump post_n
    version="$(uvx bump-my-version show current_version)"
    git add -A
    git commit -m "Bump version: $(uvx bump-my-version show current_version --increment post_n) → ${version}"
    git tag "v${version}"
    git push && git push --tags
