#!/bin/bash
#
# execute each perl .t test individually and grab its coverage.
# Clears gcda between runs so each test starts clean.
#
# Needs HTTPD_ROOT and PERL_FRAMEWORK set.

set -e

: "${HTTPD_ROOT:?HTTPD_ROOT not set}"
: "${PERL_FRAMEWORK:?PERL_FRAMEWORK not set}"

outdir=$HTTPD_ROOT/coverage/per_test/perl
mkdir -p "$outdir/raw" "$outdir/norm"

cd "$HTTPD_ROOT"

total=0
ok=0
fail=0

find "$PERL_FRAMEWORK/t" -name '*.t' -type f | sort | while read -r tfile; do
  rel=${tfile#$PERL_FRAMEWORK/}

  # change t/apache/headers.t into apache__headers (had difficulties to recognize test)
  name=${rel#t/}
  name=${name%.t}
  name=${name//\//__}

  total=$((total + 1))
  echo "--- [$total] $rel ($name) ---"

  # stop leftover httpd, delete .gdca
  (cd "$PERL_FRAMEWORK" && ./t/TEST -stop 2>/dev/null || true)
  "$HTTPD_ROOT/coverage/tools/clean_gcda.sh"

  # run individual test
  if ! (cd "$PERL_FRAMEWORK" && ./t/TEST -verbose "$rel"); then
    echo "$rel failed, collecting coverage anyway"
  fi

  # stop httpd to get gcda flushed
  (cd "$PERL_FRAMEWORK" && ./t/TEST -stop 2>/dev/null || true)

  # capture coverage
  if gcovr -r "$HTTPD_ROOT" \
       --config /dev/null \
       --gcov-ignore-errors all \
       --gcov-ignore-parse-errors all \
       --exclude 'conftest(\.c|\.gcno|\.gcda)?$' \
       --exclude 'modules/apreq/' \
       --json "$outdir/raw/${name}.json"; then

    # normalize coverage
    python "$HTTPD_ROOT/coverage/tools/normalize_gcovr.py" \
      "$outdir/raw/${name}.json" \
      "$outdir/norm/${name}.json"
    ok=$((ok + 1))
  else
    echo "gcovr failed for $rel"
    fail=$((fail + 1))
  fi

  echo
done

echo "done: $total tests, $ok ok, $fail failed"
