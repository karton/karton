#! /bin/bash

TARGETS="\
    ubuntu:latest \
    "

function _error() {
    echo "$1" >&2
    exit 1
}

package_path="$1"

if [ -z "$package_path" ]; then
    _error "You must specify a package to run."
fi

package=$(basename "$package_path")
base_package_name=$(echo "$package" | sed 's,.tar.gz$,,')

rm test-results/inception-*.json 2> /dev/null

script_path=$(mktemp)

cat > $script_path << EOF
#! /bin/bash

set -e

base_package_name="$1"
package="$base_package_name.tar.gz"

tar xzf "$package"
cd "$base_package_name"

python ./tests/run.py --save-json-results ../test-results.json
EOF

for target in $TARGETS; do
    ./inception/inception.py \
        --add "$package_path" _ \
        --save-back "test-results/inception-$target.json"  "test-results.json" \
        --add-script "$script_path" "run.sh" \
        "$target" \
        "./run.sh" "$base_package_name"
done

