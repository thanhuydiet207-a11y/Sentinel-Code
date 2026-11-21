"""Offline multi-reviewer consensus for AI-assisted security findings.

This module does not call AI providers and never suppresses findings. It validates
reviewer outputs and summarizes agreement for a human security reviewer.
"""
from __future__ import annotations

import math
from typing import Any

VERDICTS = ("confirmed", "likely", "uncertain", "dismissed")
POSITIVE = ("confirmed", "likely")


class ReviewValidationError(ValueError):
    """Raised for malformed reviewer packages or invalid finding references."""


def aggregate_reviews(findings_payload: dict[str, Any], reviews_payload: dict[str, Any]) -> dict[str, Any]:
    findings = findings_payload.get("findings")
    reviewers = reviews_payload.get("reviewers")
    if not isinstance(findings, list):
        raise ReviewValidationError("findings payload must contain a findings array")
    if not isinstance(reviewers, list):
        raise ReviewValidationError("reviews payload must contain a reviewers array")

    finding_map: dict[str, dict[str, Any]] = {}
    for item in findings:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item["id"]:
            raise ReviewValidationError("each finding must be an object with a non-empty id")
        if item["id"] in finding_map:
            raise ReviewValidationError(f"duplicate finding id: {item['id']}")
        finding_map[item["id"]] = item

    reviewer_ids: set[str] = set()
    votes: dict[str, list[dict[str, Any]]] = {fid: [] for fid in finding_map}
    total_votes = 0
    for reviewer in reviewers:
        if not isinstance(reviewer, dict):
            raise ReviewValidationError("reviewer entry must be an object")
        rid = reviewer.get("reviewer_id")
        provider = reviewer.get("provider")
        if not isinstance(rid, str) or not rid.strip() or len(rid) > 128:
            raise ReviewValidationError("reviewer_id must be a non-empty string up to 128 chars")
        if rid in reviewer_ids:
            raise ReviewValidationError(f"duplicate reviewer_id: {rid}")
        reviewer_ids.add(rid)
        if not isinstance(provider, str) or not provider.strip() or len(provider) > 80:
            raise ReviewValidationError(f"reviewer {rid}: provider must be a non-empty string up to 80 chars")
        review_list = reviewer.get("reviews")
        if not isinstance(review_list, list):
            raise ReviewValidationError(f"reviewer {rid}: reviews must be an array")
        reviewed: set[str] = set()
        for vote in review_list:
            if not isinstance(vote, dict):
                raise ReviewValidationError(f"reviewer {rid}: vote must be an object")
            fid = vote.get("finding_id")
            if fid not in finding_map:
                raise ReviewValidationError(f"reviewer {rid}: unknown finding_id {fid!r}")
            if fid in reviewed:
                raise ReviewValidationError(f"reviewer {rid}: duplicate vote for {fid}")
            reviewed.add(fid)
            verdict = vote.get("verdict")
            if verdict not in VERDICTS:
                raise ReviewValidationError(f"reviewer {rid}: verdict must be one of {', '.join(VERDICTS)}")
            confidence = vote.get("confidence")
            if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not math.isfinite(confidence) or not 0 <= confidence <= 1:
                raise ReviewValidationError(f"reviewer {rid}: confidence must be finite and between 0 and 1")
            rationale = vote.get("rationale", "")
            if not isinstance(rationale, str) or len(rationale) > 2000:
                raise ReviewValidationError(f"reviewer {rid}: rationale must be a string up to 2000 chars")
            evidence_refs = vote.get("evidence_refs", [])
            if not isinstance(evidence_refs, list) or any(not isinstance(ref, str) or len(ref) > 500 for ref in evidence_refs):
                raise ReviewValidationError(f"reviewer {rid}: evidence_refs must be an array of strings up to 500 chars")
            votes[fid].append({
                "reviewer_id": rid,
                "provider": provider,
                "model": reviewer.get("model") if isinstance(reviewer.get("model"), str) else None,
                "verdict": verdict,
                "confidence": float(confidence),
                "rationale": rationale,
                "evidence_refs": evidence_refs,
            })
            total_votes += 1

    results = []
    for fid, finding in finding_map.items():
        entries = votes[fid]
        counts = {verdict: sum(1 for vote in entries if vote["verdict"] == verdict) for verdict in VERDICTS}
        if not entries:
            agreement = 0.0
            dominant = "no_review"
            disagreement = False
        else:
            dominant, dominant_count = max(counts.items(), key=lambda pair: (pair[1], -VERDICTS.index(pair[0])))
            agreement = round(dominant_count / len(entries), 4)
            disagreement = len({entry["verdict"] for entry in entries}) > 1
        positive_count = counts["confirmed"] + counts["likely"]
        results.append({
            "finding_id": fid,
            "title": finding.get("title", ""),
            "location": finding.get("location", {}),
            "severity": finding.get("severity", "unknown"),
            "review_count": len(entries),
            "verdict_counts": counts,
            "dominant_verdict": dominant,
            "agreement_ratio": agreement,
            "disagreement": disagreement,
            "positive_review_count": positive_count,
            "positive_corroborated": positive_count >= 2,
            "reviews": entries,
            "recommendation": "manual_review",
            "automatic_suppression": False,
        })

    return {
        "schema_version": "1.0",
        "metadata": {
            "finding_count": len(finding_map),
            "reviewer_count": len(reviewer_ids),
            "vote_count": total_votes,
            "method": "unweighted reviewer vote counts; agreement ratio is descriptive, not calibrated",
            "automatic_suppression": False,
        },
        "consensus": results,
        "safety_note": "AI reviewer agreement is not proof of exploitability or safety. Dismissed findings remain available for human review; no finding is automatically suppressed.",
    }
