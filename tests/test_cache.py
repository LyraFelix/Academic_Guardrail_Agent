"""Unit tests for SqliteCache."""

import time
import tempfile
import os
import pytest
from academic_guardrail.core.cache import SqliteCache


@pytest.fixture()
def tmp_cache(tmp_path):
    db = str(tmp_path / "test_cache.db")
    return SqliteCache(db_path=db, ttl_seconds=60)


def test_set_and_get(tmp_cache):
    tmp_cache.set("k1", {"value": 42})
    result = tmp_cache.get("k1")
    assert result == {"value": 42}


def test_get_missing_returns_none(tmp_cache):
    assert tmp_cache.get("nonexistent") is None


def test_ttl_expiry(tmp_cache):
    # Set with a very short TTL of 1 second
    tmp_cache.set("k_short", "expire_me", ttl_seconds=1)
    assert tmp_cache.get("k_short") == "expire_me"
    time.sleep(1.1)
    assert tmp_cache.get("k_short") is None


def test_overwrite_existing(tmp_cache):
    tmp_cache.set("k2", "old")
    tmp_cache.set("k2", "new")
    assert tmp_cache.get("k2") == "new"


def test_delete(tmp_cache):
    tmp_cache.set("k3", "delete_me")
    tmp_cache.delete("k3")
    assert tmp_cache.get("k3") is None


def test_purge_expired(tmp_cache):
    tmp_cache.set("a", "v1", ttl_seconds=1)
    tmp_cache.set("b", "v2", ttl_seconds=60)
    time.sleep(1.1)
    removed = tmp_cache.purge_expired()
    assert removed == 1
    assert tmp_cache.get("b") == "v2"


def test_stats(tmp_cache):
    tmp_cache.set("s1", 1)
    tmp_cache.set("s2", 2)
    stats = tmp_cache.stats()
    assert stats["total"] == 2
    assert stats["valid"] == 2
    assert stats["expired"] == 0


def test_make_key_stable():
    key1 = SqliteCache.make_key("ns", "DOI:10.1234/abc", "extra")
    key2 = SqliteCache.make_key("ns", "DOI:10.1234/abc", "extra")
    assert key1 == key2
    # Different namespace => different key
    key3 = SqliteCache.make_key("other", "DOI:10.1234/abc", "extra")
    assert key1 != key3


def test_clear(tmp_cache):
    tmp_cache.set("c1", 1)
    tmp_cache.set("c2", 2)
    tmp_cache.clear()
    assert tmp_cache.get("c1") is None
    assert tmp_cache.stats()["total"] == 0
