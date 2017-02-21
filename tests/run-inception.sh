#! /bin/bash

TARGETS=""

# Ubuntu.
TARGETS+=" ubuntu:latest" # Latest LTS, not latest release.
TARGETS+=" ubuntu:devel"
# The previous LTS (14.04, Trusty Tahr) has an acient Docker.

# Debian.
# At the moment, Debian stable and older don't have a working Docker while
# unstable at some point broke Docker. I'm not sure it's worth the effort
# as we test two Ubuntu versions.
# We could test with the official packages, but... meh.
# TARGETS+=" debian:unstable"

# CentOS.
TARGETS+=" centos:latest" # This is 7 at the time of writing.
# 6 is ancient (first released in 2011)

function _error() {
    echo >&2
    echo "$1" >&2
    echo >&2
    exit 1
}

package_path="$1"
shift
if [ -z "$package_path" ]; then
    _error "You must specify a package to run."
fi

chosen_targets="$1"
shift
if [ -z "$chosen_targets" -o "$chosen_targets" = "all" ]; then
    chosen_targets="$TARGETS"
else
    for t1 in $chosen_targets; do
        ok="false"
        for t2 in $TARGETS; do
            if [ "$t1" = "$t2" ]; then
                ok="true"
                break
            fi
        done
        if [ "$ok" = "false" ]; then
            _error "'$t1' is an invalid test target."
        fi
    done
fi

tests_to_run="$@"
if [ -n "$tests_to_run" ]; then
    # We save results only if all tests were run.
    save_result=""
else
    save_result="--save-json-results ../test-results.json"
fi
if [ "$tests_to_run" = "sanity" ]; then
    run_sanity_only="true"
    tests_to_run="FAIL" # If we accidentally run the normal ones, it will fail.
else
    run_sanity_only="false"
fi

package=$(basename "$package_path")
base_package_name=$(echo "$package" | sed 's,.tar.gz$,,')

rm test-results/inception-*.json 2> /dev/null
rm test-results/sanity-*.log 2> /dev/null

main_script_path=$(mktemp)
sanity_script_path=$(mktemp)

if [ -n "$V" ]; then
    maybe_verbose="-v"
else
    maybe_verbose=""
fi

cat > $main_script_path << EOF
#! /bin/bash

set -e

tar xzf "$package"
cd "$base_package_name"

do_sanity_check="false"

if [ "$run_sanity_only" = "true" ]; then
    echo "Not running any unit test"
    do_sanity_check="true"
    echo "NOT RUN" > ../test-results.json
else
    touch ../test-results.json
    if python ./tests/run.py $maybe_verbose $save_result $tests_to_run; then
        do_sanity_check="true"
    fi
    # Run sanity checks only if all tests were run.
    if [ -n "$tests_to_run" ]; then
        do_sanity_check="false"
    fi
fi

cd ..

if [ "\$do_sanity_check" != "true" ]; then
    echo "SKIPPED" > sanity-results.log
    exit 0
fi

# Set the status as failed. This will be overwritten later if everything works.
echo "FAILED" > sanity-results.log
echo >> sanity-results.log
echo 'OUTPUT OF THE SCRIPT:' >> sanity-results.log
echo '~~~~~~~~~~~~~~~~~~~~~' >> sanity-results.log
echo >> sanity-results.log

./sanity.sh 2>&1 | tee --append --ignore-interrupts sanity-results.log

if [ \${PIPESTATUS[0]} -eq 0 ]; then
    # Overwrite the temporary failed stuff now that we know it did work.
    echo "PASSED" > sanity-results.log
fi
EOF

cat > $sanity_script_path << EOF
set -e

echo "INSTALLING"
cd "$base_package_name"
sudo python setup.py install
cd ..
echo

echo "REMOVING PACKAGE AND STUFF"
rm -r "$base_package_name"
rm -r "$package"
echo

echo "INFO"
echo "Karton is now available at \$(which karton)"
echo

echo "KARTON HELP"
karton help
echo

echo "KARTON --VERSION"
karton --version
echo

echo "KARTON IMAGE IMPORT"
mkdir definition-dir/
cat > definition-dir/definition.py << END
import os

def setup_image(props):
    print 'Running setup_image()'
    assert props
    props.user_home = '/testHome/'
    props.username = 'sanity-user'
    props.share_path('/inception/sanity-home-dir',
                     os.path.join(props.user_home, 'subdir'))
END
mkdir sanity-home-dir
karton image import sanity-image definition-dir/
echo

echo "KARTON BUILD ..."
karton build sanity-image
echo

echo "KARTON RUN ..."
if karton run sanity-image true 2> /dev/null; then
    echo "Run should have failed as \$PWD is not shared."
    exit 1
fi
cd sanity-home-dir
curr_dir=\$(karton run sanity-image pwd)
if [[ "\$curr_dir" != *"/testHome/subdir"* ]]; then
    echo "Current directory inside the sanity image is wrong: \$curr_dir"
    exit 1
fi
uname=\$(karton run sanity-image uname)
if [[ \$uname != "Linux"* ]]; then
    echo "Wrong uname output: \$uname?"
    exit 1
fi
issue=\$(karton run sanity-image cat /etc/issue)
if [[ \$issue != *"Ubuntu"* ]]; then
    echo "Wrong /etc/issue content: \$issue"
    exit 1
fi
echo
EOF

for target in $chosen_targets; do
    echo "TESTING ON TARGET $target"
    ./inception/inception.py \
        --add "$package_path" _ \
        --save-back "test-results/inception-$target.json"  "test-results.json" \
        --save-back "test-results/sanity-$target.log"  "sanity-results.log" \
        --add-script "$main_script_path" "run.sh" \
        --add-script "$sanity_script_path" "sanity.sh" \
        "$target" \
        "./run.sh"
done
