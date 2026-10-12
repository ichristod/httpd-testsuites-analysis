#
# config.py - shared tunable values, read by analyze_consolidation.py,
# compare_ranking_robustness.py, dashboard.py, and presentation/coverage_stats.py
#

# changes real numbers: which test ranks #1, the module/infra split in the
# ranking, the Focus tabs' breakdown. Doesn't touch the Overview tab totals
# (Perl Covered, Python Covered, 35/27/37%) - those come straight from the
# coverage data either way.

# % of the 206 Perl tests (accumulated across all per-test runs) a line
# needs to be hit by to count as shared infra instead of module-specific
FREQ_THRESHOLD = 0.25

# paths excluded as infra under --rank-mode path
PATH_INFRA_PREFIXES = ["server/", "os/", "include/"]

# dashboard labels from here down - applied after coverage is already
# decided, never change a number

# colors the Shared Infrastructure tab's chart "Server core" vs "Module"
CORE_FILES = [
    "core.c", "event.c", "config.c", "http_filters.c", "protocol.c",
    "request.c", "http_protocol.c", "util.c", "util_filter.c",
    "scoreboard.c", "log.c", "vhost.c", "mpm_common.c", "mpm_fdqueue.c",
]

# labels why a line is still untested, for lines already untested by both
# suites. tools_prefix catches support/ tools nobody's written a test for
# (htpasswd, rotatelogs, ...) - doesn't touch ab.c, which Perl's ab/base
# test covers fine. ldap_keyword works the same way - LDAP tests do run
# (util_ldap.c has real Perl coverage), this just labels whatever's left
UNTESTED_CATEGORIES = {
    "platform_keywords": ["win32", "netware", "os2"],
    "tools_prefix": "support/",
    "ldap_keyword": "ldap",
    "unselected_mpms": ["motorz", "simple", "prefork", "worker"],
}
