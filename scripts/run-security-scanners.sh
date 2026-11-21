#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${1:-$ROOT/.sentinel-scans}"
mkdir -p "$OUT"
cd "$ROOT"
for tool in semgrep gitleaks trivy python3; do
  command -v "$tool" >/dev/null 2>&1 || { echo "Missing scanner dependency: $tool" >&2; exit 127; }
done
run_scanner() {
  local name="$1"; shift
  set +e
  "$@"
  local status=$?
  set -e
  if [[ "$status" -gt 1 ]]; then echo "$name failed with exit code $status" >&2; return "$status"; fi
}
run_scanner semgrep semgrep scan --json --output "$OUT/semgrep.json" .
run_scanner gitleaks gitleaks detect --source . --report-format json --report-path "$OUT/gitleaks.json"
run_scanner trivy trivy fs --format json --output "$OUT/trivy.json" --scanners vuln,secret,misconfig .
python3 -m sentinel_core import-scanner semgrep "$OUT/semgrep.json" --root . --output "$OUT/findings-semgrep.json"
python3 -m sentinel_core import-scanner gitleaks "$OUT/gitleaks.json" --root . --output "$OUT/findings-gitleaks.json"
python3 -m sentinel_core import-scanner trivy "$OUT/trivy.json" --root . --output "$OUT/findings-trivy.json"
python3 - "$OUT" <<'PY'
import json, pathlib, sys
from sentinel_core.core import deduplicate_findings, validate_payload, render_markdown_report
root = pathlib.Path(".").resolve()
out = pathlib.Path(sys.argv[1])
all_findings, skipped = [], {}
for scanner in ("semgrep", "gitleaks", "trivy"):
    payload = json.loads((out / f"findings-{scanner}.json").read_text())
    all_findings.extend(payload.get("findings", []))
    skipped[scanner] = payload.get("metadata", {}).get("skipped", [])
payload = {"schema_version": "1.0", "metadata": {"source": "automated-scanner-pipeline", "scanners": ["semgrep", "gitleaks", "trivy"], "skipped": skipped}, "findings": deduplicate_findings(all_findings)}
errors = validate_payload(payload, root)
if errors: raise SystemExit("Combined findings failed evidence validation:\\n" + "\\n".join(errors))
(out / "findings-combined.json").write_text(json.dumps(payload, indent=2) + "\\n")
(out / "report.md").write_text(render_markdown_report(payload["findings"], "Automated repository scan"))
print(f"Validated and deduplicated {len(payload['findings'])} finding(s)")
print(f"Skipped records: {sum(map(len, skipped.values()))}")
PY
