# httpd-testsuites-analysis
Inspect httpd's Perl and Python test suites side by side, providing insights on coverage comparison, overlap analysis, and migration prioritization.

The project is a work in progress but even know you can get some insights.

## What this does

Apache httpd has two test suites: the old Perl-based httpd-tests and the
newer Python-based pyhttpd. The scripts here collect code coverage from
both, compare them at the line level, and rank which Perl tests are worth
migrating to Python first. There's also a Streamlit dashboard to poke
around the results.

## Prerequisites

- Linux (tested on Fedora 43)
- gcc with gcov support
- gcovr
- Python 3.11+ with pip/venv
- Perl with cpanm
- APR and APR-util dev headers

System packages (Fedora):

    sudo dnf install autoconf automake perl-App-cpanminus libtool libtool-ltdl-devel \
        apr-devel apr-util-devel openssl-devel lua-devel brotli-devel \
        libcurl-devel libnghttp2-devel jansson-devel pcre2-devel \
        libxml2-devel cyrus-sasl-devel gdb perl-doc nghttp2 curl \
        check-devel python3-pip expat-devel

On Fedora `buildconf` might fail looking for APR m4 macros. If it
complains about missing `apr_common.m4`:

    sudo mkdir -p /usr/lib64/apr-1/build
    sudo ln -s /usr/share/aclocal/apr_common.m4 /usr/lib64/apr-1/build/
    sudo ln -s /usr/share/aclocal/find_apr.m4 /usr/lib64/apr-1/build/
    sudo ln -s /usr/share/aclocal/find_apu.m4 /usr/lib64/apr-1/build/

Perl CPAN modules:

    sudo cpanm --notest Net::SSL LWP::Protocol::https \
        LWP::Protocol::AnyEvent::http ExtUtils::Embed Test::More \
        AnyEvent DateTime HTTP::DAV FCGI \
        AnyEvent::WebSocket::Client Apache::Test

Python venv (inside this repo):

    python3 -m venv .venv
    source .venv/bin/activate
    pip install pytest==8.4.2 cryptography pyopenssl requests python-multipart filelock \
        websockets gcovr streamlit pandas

## Setup

Clone httpd, this repo and httpd-tests:

    git clone https://github.com/apache/httpd.git
    git clone https://github.com/ichristod/httpd-testsuites-analysis.git
    git clone https://github.com/apache/httpd-tests.git

You need three env vars:

    export PREFIX=$HOME/build/httpd
    export HTTPD_ROOT=$HOME/gitrepos/httpd
    export PERL_FRAMEWORK=$HOME/gitrepos/httpd-tests

Create the output dirs (from the repo root):

    mkdir -p coverage/{raw,processed,metrics,lcov,per_test}

## Build httpd with coverage

    cd $HTTPD_ROOT

    ./buildconf --with-apr=/usr/bin/apr-1-config

    ./configure --prefix=$PREFIX \
        --enable-mods-shared=reallyall \
        --with-mpm=event \
        --enable-mpms-shared=all \
        --enable-load-all-modules \
        --with-apr=/usr \
        --with-apr-util=/usr \
        CFLAGS="-g -O0 --coverage" \
        LDFLAGS="--coverage"

    make -j2
    make install

## Collect Perl suite coverage

    cd $PERL_FRAMEWORK
    perl Makefile.PL -apxs $PREFIX/bin/apxs
    make test
    cd $HTTPD_ROOT

Stop httpd so gcda files get flushed:

    $PERL_FRAMEWORK/t/TEST -stop 2>/dev/null || true

Then grab coverage (run these from the analysis repo root):

    gcovr -r $HTTPD_ROOT \
        --gcov-ignore-errors all \
        --gcov-ignore-parse-errors all \
        --exclude 'conftest' --exclude 'modules/apreq/' \
        --json coverage/raw/perl.json

    gcovr -r $HTTPD_ROOT \
        --gcov-ignore-errors all \
        --gcov-ignore-parse-errors all \
        --exclude 'conftest' --exclude 'modules/apreq/' \
        --lcov coverage/lcov/perl.lcov

    python coverage/tools/normalize_gcovr.py \
        coverage/raw/perl.json \
        coverage/processed/perl.norm.json

Clean gcov data before running the other suite:

    coverage/tools/clean_gcda.sh

## Collect Python suite coverage

Build test clients first:

    cd $HTTPD_ROOT/test/clients && make
    cd $HTTPD_ROOT

    export MPM=event
    pytest test/modules/core test/modules/http1 test/modules/http2 \
        test/modules/proxy test/modules/md

Same for python:

    gcovr -r $HTTPD_ROOT \
        --gcov-ignore-errors all \
        --gcov-ignore-parse-errors all \
        --exclude 'conftest' --exclude 'modules/apreq/' \
        --json coverage/raw/python.json

    gcovr -r $HTTPD_ROOT \
        --gcov-ignore-errors all \
        --gcov-ignore-parse-errors all \
        --exclude 'conftest' --exclude 'modules/apreq/' \
        --lcov coverage/lcov/python.lcov

    python coverage/tools/normalize_gcovr.py \
        coverage/raw/python.json \
        coverage/processed/python.norm.json

## Coverage diff

    python coverage/tools/coverage_diff.py \
        coverage/processed/perl.norm.json \
        coverage/processed/python.norm.json \
        coverage/metrics/perl_only.json

Gives you a JSON of lines covered only by Perl.
Swap the arguments to get Python-only lines.

## Per-test coverage

This runs each Perl .t file one by one and grabs its coverage:

    coverage/tools/create_per_test.sh

Results end up in
`coverage/per_test/perl/`.

Inspect and analyze results:

    python coverage/tools/analyze_per_test.py \
        coverage/per_test/perl/norm

    python coverage/tools/analyze_consolidation.py \
        coverage/per_test/perl/norm \
        coverage/processed/python.norm.json \
        --json coverage/per_test/perl/consolidation_ranking.json

## Dashboard

    streamlit run coverage/tools/dashboard.py

Five tabs: Overview, Python Focus, Perl Focus, Shared Infrastructure,
and Consolidation.

## Scripts

| Script | Purpose |
|--------|---------|
| `coverage/tools/normalize_gcovr.py` | Strips raw gcovr JSON down to `{file: [lines]}` |
| `coverage/tools/clean_gcda.sh` | Wipes `.gcda` files to reset counters |
| `coverage/tools/coverage_diff.py` | Lines in suite A but not B |
| `coverage/tools/create_per_test.sh` | Runs each Perl test individually, grabs coverage |
| `coverage/tools/analyze_per_test.py` | Greedy set-cover ranking of Perl tests |
| `coverage/tools/analyze_consolidation.py` | Migration priority ranking (gap-scoped) |
| `coverage/tools/dashboard.py` | Streamlit dashboard |

