"""Offline tests for reconcile_reserves listing completeness (fake HTTP, no network)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "scripts"))
sys.path.insert(0, str(Path(__file__).parent))

import reconcile_reserves as rr  # noqa: E402

T = lambda n: f"{n:064x}"  # noqa: E731


class _Resp:
    status_code = 200

    def __init__(self, body):
        self._b = body

    def raise_for_status(self):
        pass

    def json(self):
        return self._b


def _run_pages(pages, floor=1000):
    it = iter(pages)
    rr._get = lambda *a, **k: _Resp(next(it))  # type: ignore[assignment]
    rr.time.sleep = lambda *_: None
    return rr._fetch_confirmed_unspent("1" * 30, floor, 1000, 5)


def item(n, value, height=100):
    return {"txid": T(n), "vout": 0, "value": value, "block_height": height}


def expect_raises(pages):
    try:
        _run_pages(pages)
    except RuntimeError:
        return
    raise AssertionError("expected RuntimeError")


def test_complete_set_stops_at_floor_and_after_page_scan():
    got = _run_pages([{"items": [item(1, 5000), item(2, 2000), item(3, 999)], "hasMore": True, "cursor": "x"}])
    assert set(got.values()) == {5000, 2000}


def test_exhausted_listing_is_complete():
    got = _run_pages([{"items": [item(1, 5000)], "hasMore": False, "cursor": None}])
    assert len(got) == 1


def test_has_more_without_cursor_refuses():
    expect_raises([{"items": [item(1, 5000)], "hasMore": True, "cursor": None}])


def test_missing_has_more_refuses():
    expect_raises([{"items": [item(1, 5000)]}])


def test_unconfirmed_or_malformed_item_refuses():
    expect_raises([{"items": [item(1, 5000, height=0)], "hasMore": False}])
    expect_raises([{"items": [{"txid": "zz", "vout": 0, "value": 5000, "block_height": 5}], "hasMore": False}])
    expect_raises([{"items": [{"vout": 0, "value": 5000, "block_height": 5}], "hasMore": False}])


def test_order_violation_after_floor_on_same_page_refuses():
    expect_raises([{"items": [item(1, 5000), item(2, 500), item(3, 4000)], "hasMore": True, "cursor": "x"}])


def test_max_pages_without_floor_refuses():
    pages = [{"items": [item(i, 9000 - i)], "hasMore": True, "cursor": "c"} for i in range(10)]
    expect_raises(pages)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("RECONCILE_LISTING_OK")
