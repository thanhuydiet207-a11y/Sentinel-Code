#!/usr/bin/env python3
"""Validate labeled source fixtures and ground-truth locations for the seed benchmark."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "benchmarks/security-review-v1.json"


def main() -> int:
    try:
        data = json.loads(DATASET.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"FAIL: cannot read benchmark: {exc}", file=sys.stderr)
        return 1
    cases = data.get("cases") if isinstance(data, dict) else None
    if not isinstance(cases, list) or not cases:
        print("FAIL: benchmark must contain cases", file=sys.stderr)
        return 1

    ids = set()
    vulnerable = safe = 0
    languages = set()
    for case in cases:
        cid = case.get("id")
        if not isinstance(cid, str) or not cid or cid in ids:
            print(f"FAIL: invalid or duplicate case id: {cid}", file=sys.stderr)
            return 1
        ids.add(cid)
        if case.get("label") == "vulnerable":
            vulnerable += 1
        elif case.get("label") == "safe":
            safe += 1
        else:
            print(f"FAIL: {cid} has invalid label", file=sys.stderr)
            return 1
        languages.add(case.get("language"))
        files = case.get("files")
        expected = case.get("expected_findings")
        if not isinstance(files, dict) or not files or not isinstance(expected, list):
            print(f"FAIL: {cid} must contain files and expected_findings", file=sys.stderr)
            return 1
        if case["label"] == "safe" and expected:
            print(f"FAIL: safe case {cid} has expected findings", file=sys.stderr)
            return 1
        if case["label"] == "vulnerable" and not expected:
            print(f"FAIL: vulnerable case {cid} has no expected finding", file=sys.stderr)
            return 1
        for finding in expected:
            path = finding.get("path")
            source = files.get(path)
            if not isinstance(source, str):
                print(f"FAIL: {cid} expected path is absent from files", file=sys.stderr)
                return 1
            lines = source.splitlines()
            start, end = finding.get("start_line"), finding.get("end_line")
            if not isinstance(start, int) or not isinstance(end, int) or start < 1 or end < start or end > len(lines):
                print(f"FAIL: {cid} has invalid ground-truth line range", file=sys.stderr)
                return 1
            if not isinstance(finding.get("rule_id"), str) or not isinstance(finding.get("category"), str):
                print(f"FAIL: {cid} expected finding lacks rule_id/category", file=sys.stderr)
                return 1
    if vulnerable < 1 or safe < 1 or len(languages - {None}) < 3:
        print("FAIL: benchmark requires vulnerable and safe cases across at least three languages", file=sys.stderr)
        return 1
    print(f"PASS: {len(cases)} benchmark cases; {vulnerable} vulnerable, {safe} safe, {len(languages)} languages.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
