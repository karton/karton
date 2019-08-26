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

if [[ $# = 0 ]]; then
    declare py_files=()
    # --full-name means we get the path relative to the top directory.
    # -z means that the file names are \0 separated.
    while IFS= read -r -d $'\0'; do
        if [[ "$REPLY" = *.py ]]; then
            py_files+=("$REPLY")
        fi
    done < <(git ls-files --full-name -z)
else
    py_files=("$@")
fi

[[ ${#py_files[@]} != 0 ]] || error_exit "No Python files in the repository?"

pylint \
    --rcfile=scripts/pylintrc \
    --reports=n \
    --score=n \
    "${py_files[@]}"
