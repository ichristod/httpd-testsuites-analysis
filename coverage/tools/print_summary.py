#
# print_summary.py - plain-text version of the dashboard's headline
# numbers, for anyone who doesn't want to run streamlit. Reads the same
# coverage/ JSON files dashboard.py does.
#
# usage: python3 coverage/tools/print_summary.py [coverage_root]
#
import json
import os
import sys

from config import UNTESTED_CATEGORIES

COVERAGE_ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def load_json(path):
    with open(path) as f:
        return json.load(f)


def per_file_totals(raw_path):
    raw = load_json(raw_path)
    return {f["file"]: len(f["lines"]) for f in raw["files"]}


def untested_breakdown(raw_path, py_norm, perl_norm):
    # same categorization dashboard.py's untested_composition() uses - keep
    # these in sync, they both read the buckets from config.py
    raw = load_json(raw_path)
    covered = {}
    for f, lines in perl_norm.items():
        covered.setdefault(f, set()).update(lines)
    for f, lines in py_norm.items():
        covered.setdefault(f, set()).update(lines)

    untested = {}
    for f in raw["files"]:
        fname = f["file"]
        all_lines = {l["line_number"] for l in f["lines"]}
        u = all_lines - covered.get(fname, set())
        if u:
            untested[fname] = len(u)

    total = sum(untested.values())
    if total == 0:
        return None

    def bucket(pred):
        return sum(v for k, v in untested.items() if pred(k))

    uc = UNTESTED_CATEGORIES
    platform = bucket(lambda k: any(kw in k for kw in uc["platform_keywords"]))
    tools = bucket(lambda k: k.startswith(uc["tools_prefix"]))
    ldap = bucket(lambda k: uc["ldap_keyword"] in k.lower())
    unselected_mpm = bucket(lambda k: any(f"/mpm/{m}/" in k for m in uc["unselected_mpms"]))
    explained = platform + tools + ldap + unselected_mpm
    unexplained = total - explained

    rows = [
        ("No structural explanation", unexplained),
        ("Bundled CLI tools (support/)", tools),
        ("Platform-only (Win32/NetWare/OS2)", platform),
        ("LDAP-dependent", ldap),
        ("MPMs neither suite selects", unselected_mpm),
    ]
    return total, [(name, n) for name, n in rows if n > 0]


def print_test_health(coverage_root):
    run_info_path = os.path.join(coverage_root, "run_info.json")
    if not os.path.exists(run_info_path):
        return
    health = load_json(run_info_path).get("test_health")
    if not health:
        return

    print("=== Test health (from this run's CI logs) ===")

    perl = health.get("perl")
    if perl:
        print(f"Perl: {perl['total']} tests, coverage captured for {perl['coverage_ok']}, "
              f"failed to capture for {perl['coverage_failed']}")

    for label, key in (("Python (event MPM)", "python_event_mpm"),
                        ("Python (mod_md)", "python_mod_md")):
        counts = health.get(key)
        if counts:
            parts = ", ".join(f"{n} {kind}" for kind, n in counts.items())
            print(f"{label}: {parts}")
    print()


def main():
    print_test_health(COVERAGE_ROOT)

    py_norm = load_json(os.path.join(COVERAGE_ROOT, "processed", "python.norm.json"))
    perl_norm = load_json(os.path.join(COVERAGE_ROOT, "processed", "perl.norm.json"))
    py_raw_path = os.path.join(COVERAGE_ROOT, "raw", "python.json")
    py_totals = per_file_totals(py_raw_path)

    total = sum(py_totals.values())
    py_covered = sum(len(set(lines)) for lines in py_norm.values())
    perl_covered = sum(len(set(lines)) for lines in perl_norm.values())

    overlap = 0
    for fname, lines in perl_norm.items():
        overlap += len(set(lines) & set(py_norm.get(fname, [])))
    union = py_covered + perl_covered - overlap
    py_only = py_covered - overlap
    perl_only = perl_covered - overlap

    print("=== Combined coverage (% of all executable lines) ===")
    print(f"Total executable lines: {total:,}")
    print(f"Covered by either suite: {union:,} ({union / total * 100:.1f}%)")
    print(f"Untested: {total - union:,} ({(total - union) / total * 100:.1f}%)")
    print()
    print("=== Split of the covered code (% of covered lines only) ===")
    print(f"Both suites: {overlap:,} ({overlap / union * 100:.1f}%)")
    print(f"Perl only:   {perl_only:,} ({perl_only / union * 100:.1f}%)")
    print(f"Python only: {py_only:,} ({py_only / union * 100:.1f}%)")

    breakdown = untested_breakdown(py_raw_path, py_norm, perl_norm)
    if breakdown:
        ut_total, rows = breakdown
        print()
        print("=== Untested code, grouped ===")
        for name, n in sorted(rows, key=lambda r: -r[1]):
            print(f"  {name}: {n:,} ({n / ut_total * 100:.1f}%)")

    cons_path = os.path.join(COVERAGE_ROOT, "per_test", "perl", "consolidation_ranking.json")
    if not os.path.exists(cons_path):
        print()
        print("No migration ranking found - generate it with analyze_consolidation.py --json")
        return

    cons = load_json(cons_path)
    ranking = cons["ranking"]
    contributing = [e for e in ranking if e["new_lines"] > 0]

    print()
    print("=== Migration ranking (Perl tests, gap-scoped against Python) ===")
    print(f"Gap size: {cons['summary']['gap_size']:,} lines")
    print(f"{len(ranking)} tests total, {len(contributing)} contribute new lines")
    print()

    thresholds = {}
    for t in (50, 80, 90, 95, 99, 100):
        for i, e in enumerate(ranking, 1):
            if e["pct"] >= t:
                thresholds[t] = i
                break
    for t in (50, 80, 90, 95, 99, 100):
        if t in thresholds:
            print(f"  {t}% of the gap closed after {thresholds[t]} tests")

    print()
    print("Top 10:")
    for i, e in enumerate(contributing[:10], 1):
        test = e["test"].replace("__", "/")
        print(f"  {i}. {test}: +{e['new_lines']} -> {e['pct']}%")


if __name__ == "__main__":
    main()
