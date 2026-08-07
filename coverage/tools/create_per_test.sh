#!/bin/bash
#
# execute each perl .t test individually and grab its coverage.
# Clears gcda between runs so each test starts clean.
#
# t/ssl/* is special-cased: rerun under each SSL session-cache backend
# (shmcb, redis, memcache) to exercise more of the session-cache
# subsystem than a single default-backend run would. gcda is left to
# accumulate across those backend reruns so the captured coverage for
# that test is their union; needs redis/memcached reachable at
# localhost:6379 / localhost:11211.
#
# Needs HTTPD_ROOT (httpd source tree) and PERL_FRAMEWORK set.

set -e

: "${HTTPD_ROOT:?HTTPD_ROOT not set}"
: "${PERL_FRAMEWORK:?PERL_FRAMEWORK not set}"

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
ANALYSIS_ROOT=$(cd "$SCRIPT_DIR/../.." && pwd)

outdir=$ANALYSIS_ROOT/coverage/per_test/perl
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

  # stop leftover httpd, delete .gcda
  (cd "$PERL_FRAMEWORK" && ./t/TEST -stop 2>/dev/null || true)
  "$SCRIPT_DIR/clean_gcda.sh"

  if [[ "$rel" == t/ssl/* ]]; then
    # rerun this test under each session-cache backend; gcda accumulates
    # across all three so the coverage captured below is their union
    for cache in shmcb "redis:localhost:6379" "memcache:localhost:11211"; do
      if (cd "$PERL_FRAMEWORK" && SSL_SESSCACHE="$cache" ./t/TEST -sslproto TLSv1.2 -defines TEST_SSL_SESSCACHE -start); then
        (cd "$PERL_FRAMEWORK" && ./t/TEST -verbose "$rel") || echo "$rel ($cache backend) failed, continuing"
      else
        echo "$rel ($cache backend) failed to start, skipping"
      fi
      (cd "$PERL_FRAMEWORK" && ./t/TEST -stop 2>/dev/null || true)
    done
  else
    if ! (cd "$PERL_FRAMEWORK" && ./t/TEST -verbose "$rel"); then
      echo "$rel failed, collecting coverage anyway"
    fi
  fi

  # stop httpd to get gcda flushed
  (cd "$PERL_FRAMEWORK" && ./t/TEST -stop 2>/dev/null || true)

  echo "gcda files on disk: $(find "$HTTPD_ROOT" -name '*.gcda' | wc -l)"

  # capture coverage
  if gcovr -r "$HTTPD_ROOT" \
       --config /dev/null \
       --gcov-ignore-errors all \
       --gcov-ignore-parse-errors all \
       --merge-mode-functions=merge-use-line-min \
       --exclude 'conftest(\.c|\.gcno|\.gcda)?$' \
       --exclude 'modules/apreq/' \
       --json "$outdir/raw/${name}.json"; then

    # normalize coverage
    python "$SCRIPT_DIR/normalize_gcovr.py" \
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
