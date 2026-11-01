"""Balanced diagnostic partitions must not leak repeated claims or sources."""

from collections import Counter

import pytest

from scripts.prepare_client_evaluation import select_partition


def candidates():
    return [(str(i), str(100 + i), label) for i, label in enumerate(
        ["SUPPORT", "CONTRADICT", "NEI"] * 8)]


def test_partitions_balance_classes_and_exclude_used_claims_and_documents():
    used_claims, used_documents = {"0"}, {"101"}
    first = select_partition(candidates(), 2, "discovery", used_claims, used_documents)
    second = select_partition(candidates(), 2, "validation", used_claims, used_documents)
    for rows in (first, second):
        assert Counter(row[2] for row in rows) == {"SUPPORT": 2, "CONTRADICT": 2, "NEI": 2}
    assert not {r[0] for r in first} & {r[0] for r in second}
    assert not {r[1] for r in first} & {r[1] for r in second}
    assert "0" not in {r[0] for r in first + second}
    assert "101" not in {r[1] for r in first + second}
    assert select_partition(candidates()[::-1], 2, "discovery", {"0"}, {"101"}) == first


def test_multiple_pairs_for_one_claim_or_document_cannot_fill_the_quota():
    duplicate_claims = [("same", str(i), label) for i, label in enumerate(["SUPPORT", "CONTRADICT", "NEI"])]
    duplicate_documents = [(str(i), "same", label) for i, label in enumerate(["SUPPORT", "CONTRADICT", "NEI"])]
    for rows in (duplicate_claims, duplicate_documents):
        with pytest.raises(ValueError, match="quota"):
            select_partition(rows, 1, "discovery", set(), set())
