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

function join() {
    local IFS="$1"
    shift
    echo "$*"
}

failure_count=0
total_count=0

function error_or_success() {
    ret="$1"
    echo
    if [[ "$ret" = 0 ]]; then
        echo "Success!"
    else
        echo "Failed!"
        ((failure_count++))
    fi
    ((total_count++))
    echo
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


# Pylint

echo "== PYLINT == "

pylint \
    --rcfile=scripts/pylintrc \
    --reports=n \
    --score=n \
    "${py_files[@]}"
error_or_success $?


# Pylint (Python 3 mode)

echo "== PYLINT (PYTHON 3 MODE) == "

pylint \
    --py3k \
    --disable useless-suppression \
    --rcfile=scripts/pylintrc \
    --reports=n \
    --score=n \
    "${py_files[@]}"
error_or_success $?


# Pycodestyle

echo "== PYCODESTYLE == "

pycodestyle_ignore=(
    'E123' # Closing bracket indentation. Checked by pylint.
    'E124' # Closing bracket not aligned. Pylint has different opinions.
    'E241' # Multiple spaces after colon. Allowed for dicts.
    'E261' # Two spaces before inline comment.
    'E266' # Too many "#". It's useful to define blocks of code.
    'E402' # Module level import not at the top. Checked by pylint.
    'E501' # Line too long. Checked by pylint.
    'E701' # Multiple statements in one line. Checked by pylint.
    'E722' # Bare except. Checked by pylint.
    'E731' # Do not assign lambda. Needed when defining argument to avoid a function redef error.
    'E741' # Ambiguous variable name. Pylint already checks for names.
    'W504' # Line break after binary operator. This is the recommended style (503 is the opposite).
    )
pycodestyle \
    --ignore="$(join "," "${pycodestyle_ignore[@]}")" \
    "${py_files[@]}"
error_or_success $?


# Done!

if [[ $failure_count = 0 ]]; then
    echo "All tests passed"
else
    echo "Failures: $failure_count out of $total_count tests"
fi
exit $failure_count
