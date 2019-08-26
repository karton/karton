#! /bin/bash

readonly bash_source="${BASH_SOURCE[0]:-$0}"
readonly scripts_dir=$(dirname "$bash_source")
readonly top_dir=$(realpath "$scripts_dir/..")

function error_exit() {
    for str in "$@"; do
        echo -n "$str" >&2
    done
    echo >&2

    exit 1
}

cd "$top_dir" || error_exit "Cannot change directory to $top_dir"

pylint \
    --rcfile=scripts/pylintrc \
    --reports=n \
    --score=n \
    karton/*.py \
    karton/container-code/*.py \
    tests/*.py \
    inception/*.py \
    scripts/*.py
