"""
coverage_diff.py - find lines covered by suite A but not suite B
Usage: python3 coverage_diff.py testsuiteA.json testsuiteB.json output.json

e.g.
python coverage/tools/coverage_diff.py \
    coverage/processed/perl.norm.json \
    coverage/processed/python.norm.json \
    coverage/metrics/perl_only.json
"""

import json
import sys

if len(sys.argv) != 4:
    print("usage: coverage_diff.py <a.norm.json> <b.norm.json> <out.json>",
          file=sys.stderr)
    sys.exit(1)

with open(sys.argv[1]) as f:
    a = json.load(f)
with open(sys.argv[2]) as f:
    b = json.load(f)

diff = {}
for fname, lines in a.items():
    b_lines = set(b.get(fname, []))
    only = sorted(ln for ln in lines if ln not in b_lines)
    if only:
        diff[fname] = only

with open(sys.argv[3], "w") as f:
    json.dump(diff, f, indent=2)

n_lines = sum(len(v) for v in diff.values())
print(f"{n_lines} lines across {len(diff)} files -> {sys.argv[3]}")