"""
 analyze consolidation - figure out which perl tests to migrate to python first

 same greedy set-cover as analyze_per_test but scoped to the "gap":
 lines covered by perl but NOT by python. also splits each test's
 contribution into module-specific vs infrastructure lines, and checks
 how much of each perl test python already duplicates.

 usage: python3 analyze_consolidation.py <perl_norm_dir> <python_norm.json> \
            [--top N] [--json PATH]
"""

import argparse
import json
from collections import defaultdict
from pathlib import Path


def basename(path):
    if "/" in path:
        return path.split("/")[-1]
    return path


# sort helpers to avoid lambdas
# for lists of tuples like [("core.c", 42), ("proxy.c", 10)]
def by_second(item):
    return item[1]

# for lists of dicts like [{"lines": 42}, {"lines": 10}]
def by_lines(item):
    return item["lines"]

def by_gap_lines(item):
    return item["gap_lines"]

def by_overlap_percentage(item):
    return item["overlap_percentage"]


# remove extension and transform to set
# returns something like {"modules__rewrite": {"server/core.c": {10, 20, 30}, ...}, ...}
def load_per_test(norm_dir):
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

def load_aggregate(path):
    with open(path) as f:
        raw = json.load(f)
    return {fname: set(lines) for fname, lines in raw.items()}

# how many perl tests hit each (file, line) pair
def count_line_freq(per_test):
    freq = defaultdict(int)
    for cov in per_test.values():
        for fname, lines in cov.items():
            for ln in lines:
                freq[(fname, ln)] += 1
    return freq


# lines hit by many tests = infrastructure
# lines hit by few tests = module-specific
# returns (module_count, infra_count, top_3_module_files)
def split_module_infra(lines, freq, cutoff):
    module = 0
    infra = 0
    per_file = defaultdict(int)
    for fname, ln in lines:
        if freq.get((fname, ln), 0) > cutoff:
            infra += 1
        else:
            module += 1
            per_file[basename(fname)] += 1
    top = sorted(per_file.items(), key=by_second, reverse=True)[:3]
    return module, infra, top


# remove anything python already covers from each perl test
def scope_to_gap(per_test, python_cov):
    py_flat = flatten(python_cov)
    scoped = {}
    for name, cov in per_test.items():
        gap_lines = flatten(cov) - py_flat
        scoped[name] = gap_lines
    return scoped, py_flat


# picks the next test that covers the most remaining lines
# receives something like {"test_a": {"core.c": {10, 20, 30}}, "test_b": {...}, ...}
# splits each pick into module vs infrastructure lines
def most_valuable_tests(scoped_tests, gap_size, freq, cutoff):
    covered = set()
    order = []
    remaining = dict(scoped_tests)

    while remaining:
        # find the test that covers the most uncovered gap lines
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
        percentage = round(len(covered) / gap_size * 100, 2) if gap_size else 0

        module, infra, top_files = split_module_infra(most_valuable_lines, freq, cutoff)
        order.append({
            "test": most_valuable,
            "new_lines": len(most_valuable_lines),
            "module_lines": module,
            "infra_lines": infra,
            "top_module_files": [{"file": f, "lines": n} for f, n in top_files],
            "cumulative": len(covered),
            "pct": percentage,
        })
        del remaining[most_valuable]

    # leftover tests that add nothing
    for name in sorted(remaining):
        percentage = round(len(covered) / gap_size * 100, 2) if gap_size else 0
        order.append({
            "test": name,
            "new_lines": 0,
            "module_lines": 0,
            "infra_lines": 0,
            "top_module_files": [],
            "cumulative": len(covered),
            "pct": percentage,
        })

    return order


# for each source file, how many gap lines and which tests hit them
def gap_by_file(scoped_tests):
    file_lines = defaultdict(set)
    file_tests = defaultdict(list)
    for name, lines in scoped_tests.items():
        per_file = defaultdict(int)
        for fname, ln in lines:
            file_lines[fname].add(ln)
            per_file[fname] += 1
        for fname, cnt in per_file.items():
            file_tests[fname].append({"test": name, "lines": cnt})

    result = []
    for fname in sorted(file_lines):
        tests = sorted(file_tests[fname], key=by_lines, reverse=True)
        result.append({
            "file": fname,
            "gap_lines": len(file_lines[fname]),
            "num_tests": len(tests),
            "top_test": tests[0]["test"] if tests else "",
        })
    result.sort(key=by_gap_lines, reverse=True)
    return result


# for each perl test, check how much of its "focused" coverage python
# already has.
#
# "focused" means lines that only a few perl tests hit (<=25% of all tests).
# these are what the test specifically targets. the rest is infrastructure
# (core.c, config.c, etc) that every test triggers as a side effect.
#
# a test with high focused overlap = python already tests the same thing.
# a test with low overlap = good migration candidate.
def compute_overlap(per_test, python_cov, freq_threshold=0.25):
    py_flat = flatten(python_cov)
    freq = count_line_freq(per_test)
    cutoff = int(len(per_test) * freq_threshold)

    results = []
    for name, cov in per_test.items():
        test_flat = flatten(cov)

        # split this test's lines into focused vs shared
        focused = set()
        shared = set()
        focused_per_file = defaultdict(int)
        for pair in test_flat:
            if freq[pair] <= cutoff:
                focused.add(pair)
                focused_per_file[basename(pair[0])] += 1
            else:
                shared.add(pair)

        # skip tests that are purely infrastructure
        if not focused:
            continue

        # how many of the focused lines does python also cover?
        overlap = focused & py_flat
        overlap_percentage = round(len(overlap) / len(focused) * 100, 1)

        # which files contribute to the overlap
        overlap_per_file = defaultdict(int)
        for fname, ln in overlap:
            overlap_per_file[basename(fname)] += 1

        # top 3 files for focused and overlap
        top_overlap = sorted(overlap_per_file.items(), key=by_second, reverse=True)[:3]
        top_focused = sorted(focused_per_file.items(), key=by_second, reverse=True)[:3]

        results.append({
            "test": name,
            "total_lines": len(test_flat),
            "focused_lines": len(focused),
            "shared_lines": len(shared),
            "python_overlap": len(overlap),
            "overlap_percentage": overlap_percentage,
            "unique_focused": len(focused) - len(overlap),
            "top_focused_files": [{"file": f, "lines": n} for f, n in top_focused],
            "top_overlap_files": [{"file": f, "lines": n} for f, n in top_overlap],
        })

    results.sort(key=by_overlap_percentage, reverse=True)
    return results


def main():
    p = argparse.ArgumentParser()
    p.add_argument("perl_norm_dir")
    p.add_argument("python_aggregate")
    p.add_argument("--top", type=int, default=30)
    p.add_argument("--json", metavar="PATH")
    args = p.parse_args()

    per_test = load_per_test(args.perl_norm_dir)
    python_cov = load_aggregate(args.python_aggregate)

    py_flat = flatten(python_cov)
    # remove python coverage
    scoped, _ = scope_to_gap(per_test, python_cov)

    # total gap = union of all perl-only lines
    gap = set()
    for s in scoped.values():
        gap |= s
    gap_size = len(gap)

    print(f"{len(per_test)} perl tests, python covers {len(py_flat)} lines, gap: {gap_size} lines")

    # # how many perl tests hit each (file, line) pair
    # extract how many times perl test hit (file, line) pairs
    # we need it to identify shared common files (infra)
    freq = count_line_freq(per_test)

    # lines hit by >25% of tests are infrastructure
    cutoff = int(len(per_test) * 0.25)

    order = most_valuable_tests(scoped, gap_size, freq, cutoff)
    gap_files = gap_by_file(scoped)
    overlap = compute_overlap(per_test, python_cov)

    # json export is the main point
    if args.json:
        contributing = [e for e in order if e["new_lines"] > 0]

        # per-file infrastructure ratio
        all_covered = defaultdict(set)
        for cov in per_test.values():
            for fname, lines in cov.items():
                all_covered[fname].update(lines)
        file_infra_ratio = {}
        for fname, lines in all_covered.items():
            total = len(lines)
            shared = sum(1 for ln in lines if freq[(fname, ln)] > cutoff)
            file_infra_ratio[basename(fname)] = round(shared / total * 100, 1) if total else 0

        export = {
            "summary": {
                "perl_tests": len(per_test),
                "python_lines": len(py_flat),
                "gap_size": gap_size,
                "contributing_tests": len(contributing),
            },
            "ranking": order,
            "gap_by_file": gap_files,
            "overlap": overlap,
            "file_infra_ratio": file_infra_ratio,
        }
        with open(args.json, "w") as f:
            json.dump(export, f, indent=2)
        print(f"written to {args.json}")
    else:
        # just prints
        for i, e in enumerate(order, 1):
            if e["new_lines"] > 0:
                print(f"  {i}. {e['test']}: +{e['new_lines']} ({e['module_lines']} module, {e['infra_lines']} infra) -> {e['pct']}%")
            elif i <= len([x for x in order if x["new_lines"] > 0]) + 1:
                rest = len(order) - i + 1
                print(f"  ... {rest} more with 0 new lines")
                break


if __name__ == "__main__":
    main()
