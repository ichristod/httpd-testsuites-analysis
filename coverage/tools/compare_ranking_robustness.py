"""
compare ranking robustness - sanity-check the migration ranking by
re-running it current/frequency/path (see filter_gap_lines in
analyze_consolidation.py) and comparing. standalone, not part of the
main pipeline.

usage: python3 compare_ranking_robustness.py <perl_norm_dir> <python_norm.json> \
           [--top N] [--json PATH]
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from analyze_consolidation import (  # noqa: E402
    count_line_freq,
    filter_gap_lines,
    load_aggregate,
    load_per_test,
    most_valuable_tests,
    scope_to_gap,
)

MODES = ["current", "frequency", "path"]


def rank_for_mode(per_test, python_cov, mode):
    scoped, _ = scope_to_gap(per_test, python_cov)
    freq = count_line_freq(per_test)
    cutoff = int(len(per_test) * 0.25)
    scoped = filter_gap_lines(scoped, mode, freq, cutoff)

    gap = set()
    for lines in scoped.values():
        gap |= lines
    gap_size = len(gap)

    order = most_valuable_tests(scoped, gap_size, freq, cutoff)
    contributing = [e["test"] for e in order if e["new_lines"] > 0]
    return contributing, gap_size


def first_divergence(a, b):
    for i, (x, y) in enumerate(zip(a, b), 1):
        if x != y:
            return i
    return None


def main():
    p = argparse.ArgumentParser()
    p.add_argument("perl_norm_dir")
    p.add_argument("python_aggregate")
    p.add_argument("--top", type=int, default=10)
    p.add_argument("--json", metavar="PATH")
    args = p.parse_args()

    per_test = load_per_test(args.perl_norm_dir)
    python_cov = load_aggregate(args.python_aggregate)

    rankings = {}
    gap_sizes = {}
    for mode in MODES:
        contributing, gap_size = rank_for_mode(per_test, python_cov, mode)
        rankings[mode] = contributing
        gap_sizes[mode] = gap_size

    top_n = args.top
    print(f"gap sizes (lines): current={gap_sizes['current']}  "
          f"frequency={gap_sizes['frequency']}  path={gap_sizes['path']}")
    print()
    print(f"{'#':>3}  {'current':<20} {'frequency':<20} {'path':<20}")
    for i in range(top_n):
        row = [rankings[m][i] if i < len(rankings[m]) else "-" for m in MODES]
        print(f"{i + 1:>3}  {row[0]:<20} {row[1]:<20} {row[2]:<20}")

    div_freq = first_divergence(rankings["current"], rankings["frequency"])
    div_path = first_divergence(rankings["current"], rankings["path"])

    print()
    if div_freq is None:
        print("frequency-based: identical order to current, all the way through")
    else:
        print(f"frequency-based: first diverges from current at rank {div_freq} "
              f"({rankings['current'][div_freq - 1]} vs {rankings['frequency'][div_freq - 1]})")
    if div_path is None:
        print("path-based: identical order to current, all the way through")
    else:
        print(f"path-based: first diverges from current at rank {div_path} "
              f"({rankings['current'][div_path - 1]} vs {rankings['path'][div_path - 1]})")

    if args.json:
        export = {
            "gap_sizes": gap_sizes,
            "rankings": {m: rankings[m][:top_n] for m in MODES},
            "first_divergence": {"frequency": div_freq, "path": div_path},
        }
        with open(args.json, "w") as f:
            json.dump(export, f, indent=2)
        print(f"\nwritten to {args.json}")


if __name__ == "__main__":
    main()
