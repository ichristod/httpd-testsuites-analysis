#!/usr/bin/env python3
"""export_ranking_csv.py - dump consolidation_ranking.json to a CSV someone
can open in a spreadsheet without running the pipeline themselves.

Usage:
    python3 coverage/tools/export_ranking_csv.py

Reads coverage/per_test/perl/consolidation_ranking.json and coverage/run_info.json,
writes coverage/exports/consolidation_ranking_<generated_at date>.csv. The output
filename and an in-file header row carry the run's generated_at date and run_id so
anyone using the CSV later knows exactly which run it came from (run_info.json
doesn't pin the exact httpd commit, only the branch ref, so that's what's recorded
here - not a fabricated commit date).
"""
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RANKING = ROOT / "per_test" / "perl" / "consolidation_ranking.json"
RUN_INFO = ROOT / "run_info.json"
OUT_DIR = ROOT / "exports"


def main():
    if not RANKING.exists():
        print(f"error: {RANKING} not found - run the pipeline first "
              "(see README: analyze_consolidation.py)", file=sys.stderr)
        sys.exit(1)

    data = json.loads(RANKING.read_text())
    run_info = json.loads(RUN_INFO.read_text()) if RUN_INFO.exists() else {}
    generated_at = run_info.get("generated_at", "unknown")
    run_id = run_info.get("run_id", "unknown")
    httpd_ref = run_info.get("httpd_ref", "unknown")
    date_part = generated_at.split("T")[0] if "T" in generated_at else generated_at

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / f"consolidation_ranking_{date_part}.csv"

    with open(out_path, "w", newline="") as f:
        f.write(f"# generated_at={generated_at} run_id={run_id} httpd_ref={httpd_ref} "
                f"perl_tests={data['summary']['perl_tests']} "
                f"gap_size={data['summary']['gap_size']} "
                f"contributing_tests={data['summary']['contributing_tests']}\n")
        writer = csv.writer(f)
        writer.writerow(["rank", "test", "new_lines", "module_lines", "infra_lines",
                          "cumulative", "pct", "top_module_files"])
        for i, row in enumerate(data["ranking"], 1):
            top_files = "; ".join(f'{tf["file"]}:{tf["lines"]}' for tf in row.get("top_module_files", []))
            writer.writerow([i, row["test"], row["new_lines"], row["module_lines"],
                              row["infra_lines"], row["cumulative"], row["pct"], top_files])

    print(f"wrote {out_path} ({len(data['ranking'])} rows)")


if __name__ == "__main__":
    main()
