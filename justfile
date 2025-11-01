set dotenv-load := true

# List all available commands
_default:
    @just --list --unsorted

@install:
    uv sync

@test:
    uvx pytest

@fmt:
    just --fmt --unstable
    uvx prek run -a

@dj *ARGS:
    cd demo && uv run python manage.py {{ ARGS }}

@run-demo:
    cd demo && uv run python manage.py runserver

logchanges *ARGS:
    uvx git-cliff --output CHANGELOG.md {{ ARGS }}

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
