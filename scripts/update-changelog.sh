#! /bin/bash

if [ ! -e changelog ]; then
    echo "You should run $0 from the top-level Karton dir." >&2
    exit 1
fi

tmpfile=$(mktemp)

echo "Karton $(python ./karton/version.py) - $(date '+%Y-%m-%d') $(git config user.name) <$(git config user.email)>" >> $tmpfile
echo >> $tmpfile
echo '    * [FILL ME]' >> $tmpfile
echo >> $tmpfile
cat changelog >> $tmpfile

mv $tmpfile changelog
