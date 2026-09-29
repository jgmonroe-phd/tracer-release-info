"""Exercise actual HTTP ingestion, concurrent SQLite writes, and privacy boundaries."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stderr
from http.client import HTTPConnection
import io
import json
from pathlib import Path
import socket
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from uuid import uuid4

from service.usage_server import Conflict, Store, UsageServer, validate_event


def event(**changes):
    return {
        "schema_version": 1, "event": "launch", "launch_id": str(uuid4()),
        "installation_id": str(uuid4()), "version": "0.9.11",
    } | changes


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.now = 1_800_000_000
        self.store = Store(Path(self.temp.name) / "usage.sqlite3", clock=lambda: self.now)

    def test_replay_and_conflict_do_not_inflate_counts(self):
        item = event()
        self.assertTrue(self.store.record(item))
        self.assertFalse(self.store.record(item))
        with self.assertRaises(Conflict):
            self.store.record(item | {"version": "0.9.12"})
        self.assertEqual(self.store.summary()["launches"], 1)

    def test_concurrent_replay_is_atomic(self):
        item = event()
        with ThreadPoolExecutor(max_workers=16) as pool:
            created = list(pool.map(self.store.record, [item] * 32))
        self.assertEqual(sum(created), 1)
        self.assertEqual(self.store.summary()["launches"], 1)

    def test_distinct_installations_are_not_summed_across_versions(self):
        installation = str(uuid4())
        items = [event(installation_id=installation), event(installation_id=installation, version="0.9.12"), event()]
        with ThreadPoolExecutor(max_workers=3) as pool:
            self.assertTrue(all(pool.map(self.store.record, items)))
        summary = self.store.summary()
        self.assertEqual(summary["launches"], 3)
        self.assertEqual(summary["distinct_installations"], 2)
        self.assertNotIn(installation, json.dumps(summary))
        self.assertEqual(set(summary["by_version"][0]), {"version", "launches", "distinct_installations"})

    def test_retention_is_enforced_on_summary_and_ingestion(self):
        item = event()
        self.store.record(item)
        self.now += 91 * 86400
        self.assertEqual(self.store.summary()["launches"], 0)
        self.assertTrue(self.store.record(item))  # Replay protection ends with retention.
        self.now += 91 * 86400
        self.store.record(event())
        self.assertEqual(self.store.summary()["launches"], 1)

    def test_schema_rejects_personal_fields_and_noncanonical_ids(self):
        for changes in (
            {"email": "person@example.com"}, {"filename": "secret.docx"},
            {"schema_version": True}, {"event": "report"}, {"version": "0.09.11"},
            {"launch_id": "../../file"}, {"installation_id": str(uuid4()).upper()},
            {"version": "0.9.11\n"}, {"launch_id": "00000000-0000-0000-0000-000000000000"},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                validate_event(event(**changes))


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / "usage.sqlite3")
        self.token = "test-admin-token-" + "x" * 32
        self.server = UsageServer(("127.0.0.1", 0), self.store, self.token)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.close)

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def request(self, method="POST", path="/v1/launches", body=None, headers=None):
        connection = HTTPConnection(*self.server.server_address, timeout=5)
        try:
            connection.request(method, path, body=body, headers=headers or {})
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def test_real_http_acceptance_idempotency_and_private_summary(self):
        item = event()
        body = json.dumps(item)
        headers = {"Content-Type": "application/json"}
        self.assertEqual(self.request(body=body, headers=headers), (202, {"accepted": True, "duplicate": False}))
        self.assertEqual(self.request(body=body, headers=headers), (200, {"accepted": True, "duplicate": True}))
        self.assertEqual(self.request(body=json.dumps(item | {"version": "0.9.12"}), headers=headers)[0], 409)
        self.assertEqual(self.request("GET", "/v1/summary")[0], 401)
        self.assertEqual(self.request("GET", "/v1/summary", headers={"Authorization": "Bearer wrong"})[0], 401)
        status, summary = self.request("GET", "/v1/summary", headers={"Authorization": "Bearer " + self.token})
        self.assertEqual(status, 200)
        self.assertEqual(summary["launches"], 1)
        self.assertNotIn(item["installation_id"], json.dumps(summary))

    def test_bounded_body_bad_json_and_private_fields(self):
        headers = {"Content-Type": "application/json"}
        self.assertEqual(self.request(body="x" * 1025, headers=headers)[0], 413)
        self.assertEqual(self.request(body="{bad", headers=headers)[0], 400)
        self.assertEqual(self.request(body=json.dumps(event(filename="private.docx")), headers=headers)[0], 400)
        self.assertEqual(self.request(body='{"event":"launch","event":"launch"}', headers=headers)[0], 400)
        self.assertEqual(self.request(body=json.dumps(event()))[0], 415)
        self.assertEqual(self.request(path="/v1/launches?secret=x", body=json.dumps(event()), headers=headers)[0], 404)
        self.assertEqual(self.store.summary()["launches"], 0)

    def test_requests_do_not_log_identifiers_or_ips(self):
        capture = io.StringIO()
        with redirect_stderr(capture):
            self.request(body=json.dumps(event()), headers={"Content-Type": "application/json"})
            self.request("GET", "/v1/summary?private=secret")
        self.assertEqual(capture.getvalue(), "")

    def test_bind_and_admin_secret_are_required(self):
        with self.assertRaises(ValueError):
            UsageServer(("0.0.0.0", 0), self.store, self.token)
        with self.assertRaises(ValueError):
            UsageServer(("127.0.0.1", 0), self.store, "short")

    def test_shutdown_waits_for_active_write(self):
        entered = threading.Event()
        release = threading.Event()
        closed = threading.Event()
        record = self.store.record
        results = []

        def delayed_record(item):
            entered.set()
            if not release.wait(5):
                raise RuntimeError("test did not release write")
            return record(item)

        def close_server():
            self.server.shutdown()
            self.server.server_close()
            closed.set()

        with patch.object(self.store, "record", delayed_record):
            request = threading.Thread(target=lambda: results.append(self.request(
                body=json.dumps(event()), headers={"Content-Type": "application/json"},
            )))
            request.start()
            self.assertTrue(entered.wait(2))
            close = threading.Thread(target=close_server)
            close.start()
            try:
                self.assertFalse(closed.wait(0.1))
            finally:
                release.set()
                request.join(5)
                close.join(5)
            self.assertFalse(request.is_alive())
            self.assertFalse(close.is_alive())
            self.assertTrue(closed.is_set())
            self.assertEqual(results[0][0], 202)

    def test_absolute_deadline_closes_trickled_headers_and_body(self):
        self.server.connection_deadline = 0.3
        prefixes = [
            b"POST /v1/launches HTTP/1.1\r\nX-Trickle: ",
            b"POST /v1/launches HTTP/1.1\r\nHost: localhost\r\n"
            b"Content-Type: application/json\r\nContent-Length: 1000\r\n\r\n{",
        ]
        for prefix in prefixes:
            with self.subTest(prefix=prefix):
                stop = threading.Event()
                writes = []
                with socket.create_connection(self.server.server_address, timeout=2) as connection:
                    connection.sendall(prefix)

                    def trickle():
                        while not stop.wait(0.02):
                            try:
                                connection.sendall(b"x")
                                writes.append(1)
                            except OSError:
                                return

                    sender = threading.Thread(target=trickle)
                    started = time.monotonic()
                    sender.start()
                    try:
                        while connection.recv(4096):
                            pass
                    finally:
                        stop.set()
                        sender.join(2)
                    self.assertFalse(sender.is_alive())
                    self.assertLess(time.monotonic() - started, 2)
                    self.assertGreaterEqual(len(writes), 3)
        self.assertEqual(self.store.summary()["launches"], 0)

    def test_ambiguous_framing_is_rejected_and_connection_closed(self):
        for headers in (
            b"Content-Length: 2\r\nContent-Length: 2\r\n",
            b"Content-Length: 2\r\nTransfer-Encoding:\r\n",
            b"Content-Length: -1\r\n",
            b"Content-Length: 2\r\nContent-Type: application/json\r\n",
        ):
            with self.subTest(headers=headers):
                with socket.create_connection(self.server.server_address, timeout=2) as connection:
                    connection.sendall(
                        b"POST /v1/launches HTTP/1.1\r\nHost: localhost\r\n"
                        b"Content-Type: application/json\r\n" + headers + b"\r\n{}"
                    )
                    response = b""
                    while chunk := connection.recv(4096):
                        response += chunk
                self.assertTrue(response.startswith((b"HTTP/1.0 400", b"HTTP/1.0 415")), response)
                self.assertIn(b"Connection: close", response)
        self.assertEqual(self.store.summary()["launches"], 0)


if __name__ == "__main__":
    unittest.main()
