from app.batch_progress import BatchProgress


def test_interval_summary_counts_eta_and_current_restaurant():
    output = []
    ticks = iter((0.0, 30.0, 60.0))
    progress = BatchProgress(
        "Entity Resolution", 4,
        {"cache_skip": "cache skip", "accept": "ACCEPT"},
        every=2, clock=lambda: next(ticks), emit=output.append,
    )
    progress.current(101, "첫 식당")
    progress.complete(cache_skip=1)
    assert len(output) == 1
    progress.current(102, "둘째 식당")
    progress.complete(accept=1)
    assert "2/4 (50.0%)" in output[-1]
    assert "cache skip: 1" in output[-1]
    assert "ACCEPT: 1" in output[-1]
    assert "elapsed: 30s" in output[-1]
    assert "avg: 15.0s/item" in output[-1]
    assert "ETA: 30s" in output[-1]
    progress.complete(accept=1)
    progress.complete(accept=1)
    assert "4/4 (100.0%)" in output[-1]
    assert "ETA: 0s" in output[-1]


def test_final_partial_interval_and_immediate_error():
    output = []
    progress = BatchProgress("Place ID", 3, {"matched": "MATCHED"},
                             every=10, clock=lambda: 0.0, emit=output.append)
    progress.error(429, "HTTP 429")
    assert output == ["[Place ID][ERROR] id=429 HTTP 429"]
    for _ in range(3):
        progress.complete(matched=1)
    assert "3/3 (100.0%)" in output[-1]
    assert "MATCHED: 3" in output[-1]


def test_default_ten_item_summary_can_be_configured(monkeypatch):
    output = []
    progress = BatchProgress("Detail", 11, {"success": "success"},
                             clock=lambda: 0.0, emit=output.append)
    for _ in range(9):
        progress.complete(success=1)
    assert output == []
    progress.complete(success=1)
    assert "10/11" in output[-1]
    progress.complete(success=1)
    assert "11/11" in output[-1]

    monkeypatch.setenv("BATCH_PROGRESS_EVERY", "25")
    configured = BatchProgress("Detail", 30, {"success": "success"},
                               clock=lambda: 0.0, emit=output.append)
    assert configured.every == 25
