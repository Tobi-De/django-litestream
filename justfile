set dotenv-load := true

# List all available commands
_default:
    @just --list --unsorted

@fmt:
    hatch fmt --formatter
    just --fmt --unstable
    hatch run pre-commit run reorder-python-imports -a

@dj *ARGS:
    cd demo && hatch run python manage.py {{ ARGS }}

@run-demo:
    cd demo && hatch run python manage.py runserver

# Bump project version and update changelog
bumpver VERSION:
    #!/usr/bin/env sh
    hatch run bump-my-version bump {{ VERSION }}
    hatch run git-cliff --output CHANGELOG.md

    if [ -z "$(git status --porcelain)" ]; then
        echo "No changes to commit."
        git push && git push --tags
        exit 0
    fi

    version="$(hatch version)"
    git add CHANGELOG.md
    git commit -m "Generate changelog for version ${version}"
    git tag -f "v${version}"
    git push && git push --tags
