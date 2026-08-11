"""Unit tests for Reference Resolution Benchmark suite."""

from benchmark_reference_resolution import RESOLUTION_GOLD_DATASET
from academic_guardrail.core.ref_resolver import ReferenceResolver


def test_reference_resolution_benchmark_metrics():
    resolver = ReferenceResolver()
    top1_correct = 0
    total_positive = 0
    total_abstain = 0
    abstain_correct = 0

    for item in RESOLUTION_GOLD_DATASET:
        cit = item["citation"]
        cands = item["candidates"]
        gold_doi = item["gold_doi"]
        case_type = item["type"]

        res = resolver.select_best_candidate(cit, cands, min_score=0.40)
        is_abstain_case = case_type.startswith("ABSTAIN")

        if is_abstain_case:
            total_abstain += 1
            if (res is None) or (res.get("is_uncertain") is True):
                abstain_correct += 1
        else:
            total_positive += 1
            norm_pred = resolver.normalize_doi(res.get("doi") if res else None)
            norm_gold = resolver.normalize_doi(gold_doi)
            if norm_pred == norm_gold and res.get("match_confidence") in ("HIGH", "MEDIUM"):
                top1_correct += 1

    top1_acc = top1_correct / float(total_positive)
    abstain_acc = abstain_correct / float(total_abstain)

    assert top1_acc >= 0.80
    assert abstain_acc >= 0.80
