# Patch Risk Review (Phase 4D)

    python3 -m sentinel_core review-patch-risk proposal.json --output risk.json

Input is a JSON proposal with \`path\` and \`patch\` (unified diff text). The analyzer reports path sensitivity, dependency/build changes, multi-file scope, deletion/patch size, suspicious constructs, and possible secret markers. It produces a heuristic 0–100 score and advisory level.

It does not prove maliciousness, does not validate patch correctness, and never authorizes automatic application. Review the complete diff and test results; risk scores are not calibrated probabilities.
