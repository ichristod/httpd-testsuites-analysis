"""
 analyze coverage results per test in order to identify most valuable tests (over all perl coverage)

 reads the normalized per-test json files and does:
 - per-test summary (how many files/lines each test covers)
 - greedy set-cover ranking (pick the test that adds the most new lines,
   repeat until everything is covered)
 - optional source-file-to-test mapping

 usage: python3 analyze_per_test.py <norm_dir> [--top N] [--file-map]
python3 coverage/tools/analyze_per_test.py coverage/per_test/perl/norm
"""

import argparse
import json
from collections import defaultdict
from pathlib import Path


# remove extension and transform to set
# returns something like {"modules__rewrite": {"server/core.c": {10, 20, 30}, ...}, ...}
def load_all(norm_dir):
    data = {}
    for f in sorted(Path(norm_dir).glob("*.json")):
        with open(f) as fh:
            raw = json.load(fh)
        data[f.stem] = {fname: set(lines) for fname, lines in raw.items()}
    return data


def flatten(cov):
    # turn {file: set(lines)} into a flat set of (file, line) pairs
    out = set()
    for fname, lines in cov.items():
        for ln in lines:
            out.add((fname, ln))
    return out

# picks the next test that covers the most remaining lines
# receives something like {"test_a": {"core.c": {10, 20, 30}}, "test_b": {...}, ...}
def most_valuable_tests(all_tests):
    """
    flat = {
        "test_a": {("core.c", 10), ("core.c", 20), ("core.c", 30)},
        "test_b": {("core.c", 20), ("core.c", 30), ("proxy.c", 5)},
    }"""
    flat = {name: flatten(cov) for name, cov in all_tests.items()}

    # universe get like this
    # {("core.c", 10), ("core.c", 20), ("core.c", 30), ("proxy.c", 5), ("proxy.c", 15)}
    universe = set()
    for s in flat.values():
        universe |= s
    total = len(universe)

    covered = set()
    order = []
    remaining = dict(flat)

    while remaining:
        # find the test that covers the most uncovered lines
        most_valuable = None
        most_valuable_lines = set()
        for name, lines in remaining.items():
            unique_lines = lines - covered
            if len(unique_lines) > len(most_valuable_lines):
                most_valuable = name
                most_valuable_lines = unique_lines

        if not most_valuable or not most_valuable_lines:
            break


        covered |= most_valuable_lines
        percentage = len(covered) / total * 100 if total else 0
        order.append((most_valuable, len(most_valuable_lines), len(covered), percentage))
        del remaining[most_valuable]

    # leftover tests that add nothing
    for name in sorted(remaining):
        percentage = len(covered) / total * 100 if total else 0
        order.append((name, 0, len(covered), percentage))

    return order, total

def main():
    p = argparse.ArgumentParser()
    p.add_argument("norm_dir")
    p.add_argument("--top", type=int, default=30)
    p.add_argument("--json", metavar="PATH")
    args = p.parse_args()

    all_tests = load_all(args.norm_dir)
    print(f"{len(all_tests)} tests loaded")

    # greedy set-cover
    order, total = most_valuable_tests(all_tests)

    # json export is the main point
    if args.json:
        out = []
        for i, (name, new, cum, pct) in enumerate(order, 1):
            out.append({
                "rank": i,
                "test": name,
                "new_lines": new,
                "cumulative": cum,
                "cumulative_pct": round(pct, 2),
            })
        with open(args.json, "w") as f:
            json.dump(out, f, indent=2)
        print(f"ranking written to {args.json}")
    else:
        # just prints
        for i, (name, new, cum, pct) in enumerate(order, 1):
            if i <= args.top or new > 0:
                print(f"  {i}. {name}: +{new} new, {cum} total ({pct:.1f}%)")
        print(f"{total} (file, line) pairs, {len(all_tests)} tests")


if __name__ == "__main__":
    main()
