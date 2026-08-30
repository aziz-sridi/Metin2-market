"""Tests for incremental market snapshot comparison."""

import json
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import sync.auto_sync as auto_sync
from etl.pipeline import ETLPipeline
from sync.auto_sync import SyncConfig, build_market_delta, dedupe_market_payload


def _listing(vnum: int, price: int, seller: str = "Alice") -> dict:
    return {
        "vnum": vnum,
        "yang": price,
        "seller": seller,
        "quantity": 1,
        "attrs": [],
    }


@contextmanager
def _market_feed(payload: list[dict]):
    """Serve a real local HTTP feed so requests/headers are integration-tested."""

    encoded = json.dumps(payload).encode("utf-8")

    class Handler(BaseHTTPRequestHandler):
        received_if_none_match = []

        def do_GET(self):  # noqa: N802 - BaseHTTPRequestHandler API
            validator = self.headers.get("If-None-Match")
            type(self).received_if_none_match.append(validator)
            if validator == '"market-v1"':
                self.send_response(304)
                self.send_header("ETag", '"market-v1"')
                self.end_headers()
                return

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.send_header("ETag", '"market-v1"')
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, *_args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        yield f"http://{host}:{port}/market/{{server_id}}.json", Handler
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def test_delta_separates_added_removed_and_unchanged() -> None:
    first = [_listing(10, 100), _listing(20, 200)]
    _, first_fingerprints, _, _ = build_market_delta(first, [])

    second = [_listing(10, 100), _listing(30, 300)]
    added, _, removed_count, unchanged_count = build_market_delta(
        second,
        first_fingerprints,
    )

    assert added == [_listing(30, 300)]
    assert removed_count == 1
    assert unchanged_count == 1


def test_modified_listing_is_loaded_as_a_new_version() -> None:
    original = [_listing(10, 100)]
    _, fingerprints, _, _ = build_market_delta(original, [])

    modified = [_listing(10, 125)]
    added, _, removed_count, unchanged_count = build_market_delta(modified, fingerprints)

    assert added == modified
    assert removed_count == 1
    assert unchanged_count == 0


def test_exact_duplicates_are_removed_before_loading() -> None:
    listing = _listing(10, 100)

    assert dedupe_market_payload([listing, dict(listing)]) == [listing]


def test_etl_extracts_sparse_rows_without_optional_arrays() -> None:
    pipeline = ETLPipeline(connection_string="unused")
    payload = [
        _listing(10, 100),
        {"vnum": 20, "yang": 200, "seller": "Bob", "quantity": 1},
    ]

    assert pipeline.extract(payload) is True
    assert [item.vnum for item in pipeline.extracted_items] == [10, 20]


def test_run_once_loads_only_the_second_snapshot_delta(tmp_path, monkeypatch) -> None:
    responses = iter(
        [
            [_listing(10, 100), _listing(20, 200)],
            [_listing(10, 100), _listing(30, 300)],
        ]
    )
    loaded_batches = []

    def fake_fetch(*_args, **_kwargs):
        return 200, next(responses), {"etag": "", "last_modified": ""}

    class FakePipeline:
        def __init__(self, server_id):
            self.server_id = server_id

        def run_full_pipeline(self, items):
            loaded_batches.append(items)
            return True

        def get_statistics(self):
            return {
                "extracted_items": len(loaded_batches[-1]),
                "undervalued_items": 0,
                "total_properties": 0,
                "transformation_timestamp": "test",
            }

    monkeypatch.setattr(auto_sync, "fetch_market_data", fake_fetch)
    monkeypatch.setattr(auto_sync, "ETLPipeline", FakePipeline)

    config = SyncConfig(
        server_id=502,
        url_template="https://example.test/{server_id}.json",
        state_file=tmp_path / "sync_state.json",
        interval_min_minutes=10,
        interval_max_minutes=15,
        timeout_seconds=5,
    )

    assert auto_sync.run_once(config) == 0
    assert auto_sync.run_once(config) == 0
    assert loaded_batches == [
        [_listing(10, 100), _listing(20, 200)],
        [_listing(30, 300)],
    ]

    state = json.loads(config.state_file.read_text(encoding="utf-8"))
    assert state["delta_added_count"] == 1
    assert state["delta_removed_count"] == 1
    assert state["delta_unchanged_count"] == 1


def test_run_once_honors_not_modified_response(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        auto_sync,
        "fetch_market_data",
        lambda *_args, **_kwargs: (304, None, {"etag": "abc", "last_modified": ""}),
    )

    config = SyncConfig(
        server_id=502,
        url_template="https://example.test/{server_id}.json",
        state_file=tmp_path / "sync_state.json",
        interval_min_minutes=10,
        interval_max_minutes=15,
        timeout_seconds=5,
    )

    assert auto_sync.run_once(config) == 0
    state = json.loads(config.state_file.read_text(encoding="utf-8"))
    assert state["last_http_status"] == 304
    assert state["last_load_status"] == "skipped_not_modified"


def test_run_once_fetches_real_http_json_and_reuses_etag(tmp_path, monkeypatch) -> None:
    """Exercise requests.get, JSON parsing, ETL handoff, state, and HTTP 304."""

    payload = [_listing(10, 100), _listing(20, 200)]
    loaded_batches = []

    class FakePipeline:
        def __init__(self, server_id):
            self.server_id = server_id

        def run_full_pipeline(self, items):
            loaded_batches.append(items)
            return True

        def get_statistics(self):
            return {
                "extracted_items": len(loaded_batches[-1]),
                "undervalued_items": 0,
                "total_properties": 0,
                "transformation_timestamp": "integration-test",
            }

    monkeypatch.setattr(auto_sync, "ETLPipeline", FakePipeline)

    with _market_feed(payload) as (url_template, handler):
        config = SyncConfig(
            server_id=502,
            url_template=url_template,
            state_file=tmp_path / "sync_state.json",
            interval_min_minutes=10,
            interval_max_minutes=15,
            timeout_seconds=5,
        )

        assert auto_sync.run_once(config) == 0
        assert auto_sync.run_once(config) == 0

    assert loaded_batches == [payload]
    assert handler.received_if_none_match == [None, '"market-v1"']

    state = json.loads(config.state_file.read_text(encoding="utf-8"))
    assert state["last_http_status"] == 304
    assert state["last_load_status"] == "skipped_not_modified"
    assert state["source_etag"] == '"market-v1"'
