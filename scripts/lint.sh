#! /bin/bash

if [ -e "../scripts/lint.sh" ]; then
    cd ..
fi

if [ -e "../karton/karton.py" ]; then
    cd ..
fi

if [ ! -e "./scripts/lint.sh" ]; then
    echo "You should run $0 from the top-level Karton dir." >&2
    exit 1
fi

pylint \
    --rcfile=scripts/pylintrc \
    karton/*.py \
    karton/container-code/*.py \
    tests/*.py
