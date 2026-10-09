#!/bin/sh
# Remove all .gcda files (gcov runtime counters)
# .gcno files (compile-time metadata) are left intact
set -e

find . -name '*.gcda' -delete