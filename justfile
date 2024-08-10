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
