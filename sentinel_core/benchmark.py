"""Deterministic benchmark metrics for Sentinel-Code agent findings."""
from __future__ import annotations

from collections import defaultdict
from typing import Any


def _valid_finding(item: Any) -> bool:
    if not isinstance(item, dict):
        return False
    if not isinstance(item.get("rule_id"), str) or not item["rule_id"]:
        return False
    if not isinstance(item.get("path"), str) or not item["path"]:
        return False
    start, end = item.get("start_line"), item.get("end_line")
    if not (isinstance(start, int) and not isinstance(start, bool) and start > 0
            and isinstance(end, int) and not isinstance(end, bool) and end >= start):
        return False
    if "severity" in item and item["severity"] not in ("critical", "high", "medium", "low", "info"):
        return False
    if "category" in item and not isinstance(item["category"], str):
        return False
    return True


def _dedupe(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    result = []
    for item in items:
        key = (item["rule_id"].casefold(), item["path"].replace("\\", "/"), item["start_line"], item["end_line"])
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def _matches(candidate: dict[str, Any], expected: dict[str, Any]) -> bool:
    if candidate["rule_id"].casefold() != expected["rule_id"].casefold():
        return False
    if candidate["path"].replace("\\", "/") != expected["path"].replace("\\", "/"):
        return False
    return max(candidate["start_line"], expected["start_line"]) <= min(candidate["end_line"], expected["end_line"])


def _ratio(numerator: int, denominator: int) -> float | None:
    """Return None when the metric has no denominator; never invent a perfect score."""
    return round(numerator / denominator, 4) if denominator else None


def evaluate_benchmark(dataset: dict[str, Any], results: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(dataset, dict) or not isinstance(dataset.get("cases"), list):
        raise ValueError("benchmark dataset must contain a cases array")
    if not isinstance(results, dict) or not isinstance(results.get("cases"), list):
        raise ValueError("results must contain a cases array")

    if not dataset["cases"]:
        raise ValueError("benchmark dataset must contain at least one case")
    case_by_id: dict[str, dict[str, Any]] = {}
    for case in dataset["cases"]:
        if not isinstance(case, dict) or not isinstance(case.get("id"), str):
            raise ValueError("every benchmark case must have a string id")
        if case["id"] in case_by_id:
            raise ValueError(f"duplicate dataset case id: {case['id']}")
        if case.get("label") not in ("vulnerable", "safe"):
            raise ValueError(f"{case['id']}: label must be vulnerable or safe")
        expected = case.get("expected_findings")
        if not isinstance(expected, list):
            raise ValueError(f"{case['id']}: expected_findings must be an array")
        for item in expected:
            if not _valid_finding(item):
                raise ValueError(f"{case['id']}: invalid expected finding")
        if case["label"] == "safe" and expected:
            raise ValueError(f"{case['id']}: safe cases cannot contain expected findings")
        if case["label"] == "vulnerable" and not expected:
            raise ValueError(f"{case['id']}: vulnerable cases must contain expected findings")
        case_by_id[case["id"]] = case

    result_by_id: dict[str, list[dict[str, Any]]] = {}
    for result_case in results["cases"]:
        if not isinstance(result_case, dict) or not isinstance(result_case.get("case_id"), str):
            raise ValueError("every result case must have a string case_id")
        case_id = result_case["case_id"]
        if case_id not in case_by_id:
            raise ValueError(f"unknown result case: {case_id}")
        if case_id in result_by_id:
            raise ValueError(f"duplicate result case: {case_id}")
        candidates = result_case.get("findings", [])
        if not isinstance(candidates, list) or any(not _valid_finding(item) for item in candidates):
            raise ValueError(f"{case_id}: findings contain an invalid item")
        result_by_id[case_id] = _dedupe(candidates)

    true_positive = false_positive = false_negative = 0
    matched_severity = severity_checked = 0
    safe_cases = safe_cases_with_fp = 0
    matched: list[dict[str, Any]] = []
    false_positives: list[dict[str, Any]] = []
    false_negatives: list[dict[str, Any]] = []
    categories: dict[str, dict[str, int]] = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0})

    for case_id, case in case_by_id.items():
        candidates = list(result_by_id.get(case_id, []))
        expected = list(case["expected_findings"])
        used_candidates: set[int] = set()

        for target in expected:
            candidate_index = next((i for i, candidate in enumerate(candidates)
                                    if i not in used_candidates and _matches(candidate, target)), None)
            category = target.get("category", "uncategorized")
            if candidate_index is None:
                false_negative += 1
                categories[category]["fn"] += 1
                false_negatives.append({"case_id": case_id, "expected": target})
                continue
            used_candidates.add(candidate_index)
            true_positive += 1
            categories[category]["tp"] += 1
            candidate = candidates[candidate_index]
            if isinstance(candidate.get("severity"), str) and isinstance(target.get("severity"), str):
                severity_checked += 1
                if candidate["severity"].lower() == target["severity"].lower():
                    matched_severity += 1
            matched.append({"case_id": case_id, "expected": target, "actual": candidate})

        for index, candidate in enumerate(candidates):
            if index in used_candidates:
                continue
            false_positive += 1
            category = candidate.get("category", "uncategorized")
            categories[category]["fp"] += 1
            false_positives.append({"case_id": case_id, "actual": candidate})

        if case["label"] == "safe":
            safe_cases += 1
            if candidates:
                safe_cases_with_fp += 1

    precision = _ratio(true_positive, true_positive + false_positive)
    recall = _ratio(true_positive, true_positive + false_negative)
    if precision is None and recall is None:
        f1 = None
    elif precision is None or recall is None or precision + recall == 0:
        f1 = 0.0
    else:
        f1 = round(2 * precision * recall / (precision + recall), 4)
    category_metrics = {}
    for category, counts in sorted(categories.items()):
        p = _ratio(counts["tp"], counts["tp"] + counts["fp"])
        r = _ratio(counts["tp"], counts["tp"] + counts["fn"])
        if p is None and r is None:
            category_f1 = None
        elif p is None or r is None or p + r == 0:
            category_f1 = 0.0
        else:
            category_f1 = round(2 * p * r / (p + r), 4)
        category_metrics[category] = {
            **counts, "precision": p, "recall": r, "f1": category_f1,
        }

    return {
        "benchmark_version": dataset.get("dataset_version", "unknown"),
        "agent": results.get("agent", "unspecified"),
        "summary": {
            "cases_total": len(case_by_id),
            "cases_scored": len(result_by_id),
            "unscored_case_ids": sorted(set(case_by_id) - set(result_by_id)),
            "case_coverage": _ratio(len(result_by_id), len(case_by_id)),
            "true_positive": true_positive,
            "false_positive": false_positive,
            "false_negative": false_negative,
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "safe_case_false_positive_rate": _ratio(safe_cases_with_fp, safe_cases),
            "severity_accuracy": _ratio(matched_severity, severity_checked),
            "severity_samples": severity_checked,
        },
        "by_category": category_metrics,
        "matched": matched,
        "false_positives": false_positives,
        "false_negatives": false_negatives,
    }
