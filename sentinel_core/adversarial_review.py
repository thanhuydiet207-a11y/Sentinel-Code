"""Three-stage adversarial AI review orchestration.

Each provider first reviews independently, then challenges the first-stage output,
then adjudicates both sets of reviews. All outputs remain advisory; none suppresses
a finding automatically.
"""
from __future__ import annotations

from typing import Any, Callable

from .ai_review import aggregate_reviews
from .provider_adapters import Transport, run_provider_reviews


def run_adversarial_reviews(
    findings_payload: dict[str, Any],
    providers: list[str],
    transport: Transport | None = None,
) -> dict[str, Any]:
    """Run independent, challenger, and adjudicator passes for each provider.

    This makes three provider requests per selected provider. Prior AI output is
    passed only as explicitly untrusted context to the later review roles.
    """
    if not isinstance(providers, list) or not providers:
        raise ValueError("at least one provider must be selected")
    if len(set(providers)) != len(providers):
        raise ValueError("provider list contains duplicates")

    def run_stage(role: str, prior: dict[str, Any] | None) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "review_role": role,
            "prior_reviews": prior,
            "reviewer_namespace": role,
        }
        if transport is not None:
            kwargs["transport"] = transport
        return run_provider_reviews(findings_payload, providers, **kwargs)

    independent = run_stage("independent", None)
    challenger = run_stage("challenger", {"independent": independent})
    adjudicator = run_stage("adjudicator", {
        "independent": independent,
        "challenger": challenger,
    })

    stages = {
        "independent": independent,
        "challenger": challenger,
        "adjudicator": adjudicator,
    }
    stage_consensus = {
        name: aggregate_reviews(findings_payload, package)
        for name, package in stages.items()
    }
    final_consensus = stage_consensus["adjudicator"]

    stage_votes: dict[str, dict[str, list[dict[str, str]]]] = {}
    for stage_name, package in stages.items():
        for reviewer in package["reviewers"]:
            for vote in reviewer["reviews"]:
                fid = vote["finding_id"]
                stage_votes.setdefault(fid, {}).setdefault(stage_name, []).append({
                    "provider": reviewer["provider"],
                    "reviewer_id": reviewer["reviewer_id"],
                    "verdict": vote["verdict"],
                })

    comparisons = []
    for finding in findings_payload["findings"]:
        fid = finding["id"]
        by_stage = stage_votes.get(fid, {})
        all_verdicts = {
            entry["verdict"]
            for entries in by_stage.values()
            for entry in entries
        }
        adjudicator_entries = by_stage.get("adjudicator", [])
        adjudicator_verdicts = sorted({entry["verdict"] for entry in adjudicator_entries})
        disagreement = len(all_verdicts) > 1
        comparisons.append({
            "finding_id": fid,
            "stage_verdicts": {
                name: sorted({entry["verdict"] for entry in by_stage.get(name, [])})
                for name in ("independent", "challenger", "adjudicator")
            },
            "reviewer_votes": by_stage,
            "cross_stage_disagreement": disagreement,
            "adjudicator_verdicts": adjudicator_verdicts,
            "recommendation": "manual_review" if disagreement else "human_security_decision_required",
            "automatic_suppression": False,
        })

    return {
        "schema_version": "1.0",
        "metadata": {
            "finding_count": len(findings_payload["findings"]),
            "providers": providers,
            "stages": ["independent", "challenger", "adjudicator"],
            "requests_per_provider": 3,
            "total_provider_requests": len(providers) * 3,
            "automatic_suppression": False,
        },
        "stages": stages,
        "stage_consensus": stage_consensus,
        "final_consensus": final_consensus,
        "cross_stage_analysis": comparisons,
        "safety_note": (
            "Adversarial review is advisory. Reviewer outputs are untrusted and may be wrong. "
            "Disagreement is surfaced for human review; agreement is not proof of exploitability "
            "or safety. No finding is automatically suppressed."
        ),
    }
