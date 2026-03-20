"""

Reduce gcovr JSON to {file: [executed line numbers]}.
Usage: python3 normalize_gcovr.py raw/perl.json processed/perl.norm.json

"""
import json, sys


if len(sys.argv) != 3:
    print("usage: normalize_gcovr.py <input.json> <output.json>",
          file=sys.stderr)
    sys.exit(1)

raw = json.load(open(sys.argv[1]))
result = {}

for f in raw["files"]:
    lines = [l["line_number"] for l in f["lines"] if l["count"] > 0]
    if lines:
        result[f["file"]] = sorted(lines)

json.dump(result, open(sys.argv[2], "w"), indent=2)
print(f"Normalized {len(result)} files -> {sys.argv[2]}")
