"""
merge_coverage.py - union any number of normalized coverage files into one
Usage: python3 merge_coverage.py <a.json> [b.json ...] <output.json>

e.g. combine CI's Python coverage with a locally-collected mod_md run:
python coverage/tools/merge_coverage.py \
    coverage/processed/python.norm.json \
    coverage/processed/python_md.norm.json \
    coverage/processed/python.norm.json
"""

import json
import sys

if len(sys.argv) < 3:
    print("usage: merge_coverage.py <a.json> [b.json ...] <output.json>",
          file=sys.stderr)
    sys.exit(1)

*inputs, out_path = sys.argv[1:]

merged = {}
for path in inputs:
    with open(path) as f:
        data = json.load(f)
    for fname, lines in data.items():
        merged.setdefault(fname, set()).update(lines)

result = {fname: sorted(lines) for fname, lines in merged.items()}

with open(out_path, "w") as f:
    json.dump(result, f, indent=2)

n_lines = sum(len(v) for v in result.values())
print(f"Merged {len(inputs)} files -> {len(result)} files, {n_lines} lines -> {out_path}")
