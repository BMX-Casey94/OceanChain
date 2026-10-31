"""Offline tests for the reaper's per-endpoint promotion rules."""
from broadcaster import arc_status_rank, endpoint_promotable, is_mined_status

G = arc_status_rank("SEEN_ON_NETWORK")  # 8
T = arc_status_rank("ANNOUNCED_TO_NETWORK")  # 4


def p(status, endpoint):
    return endpoint_promotable(status, endpoint, G, T)


def test_gorilla_needs_seen():
    assert not p("ACCEPTED_BY_NETWORK", "gorillapool")
    assert p("SEEN_ON_NETWORK", "gorillapool")
    assert p("SEEN_MULTIPLE_NODES", "gorillapool")


def test_taal_announced_is_enough():
    # The live TAAL statuses observed for txs GorillaPool already reports MINED.
    assert p("ANNOUNCED_TO_NETWORK", "taal")
    assert p("REQUESTED_BY_NETWORK", "taal")
    assert not p("RECEIVED", "taal")
    assert not p("STORED", "taal")


def test_orphan_mempool_never_promotes_unless_mined():
    assert not p("SEEN_IN_ORPHAN_MEMPOOL", "gorillapool")
    assert not p("SEEN_IN_ORPHAN_MEMPOOL", "taal")


def test_mined_always_promotes_on_either_endpoint():
    for ep in ("gorillapool", "taal"):
        assert p("MINED", ep)
        assert p("CONFIRMED", ep)
    assert is_mined_status("MINED") and not is_mined_status("SEEN_ON_NETWORK")


def test_unknown_or_missing_never_promotes():
    assert not p(None, "gorillapool")
    assert not p("NOT_FOUND", "taal")
    assert not p("REJECTED", "gorillapool")


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("REAPER_PROMOTION_OK")
