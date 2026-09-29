#!/usr/bin/env python3
"""Minimal launch counter; expose only through a rate-limited HTTPS reverse proxy."""

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import socket
import sqlite3
import threading
import time
from uuid import UUID


MAX_BODY = 1024
VERSION = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\Z")
FIELDS = {"schema_version", "event", "launch_id", "installation_id", "version"}


class Conflict(ValueError):
    """A launch ID has already been used with different event data."""


def validate_event(event):
    if not isinstance(event, dict) or set(event) != FIELDS:
        raise ValueError("expected exactly schema_version, event, launch_id, installation_id, version")
    if type(event["schema_version"]) is not int or event["schema_version"] != 1:
        raise ValueError("schema_version must be 1")
    if event["event"] != "launch":
        raise ValueError("event must be launch")
    for field in ("launch_id", "installation_id"):
        value = event[field]
        if not isinstance(value, str) or len(value) != 36:
            raise ValueError(f"{field} must be a canonical UUID4")
        try:
            parsed = UUID(value)
        except ValueError:
            raise ValueError(f"{field} must be a canonical UUID4") from None
        if parsed.version != 4 or str(parsed) != value:
            raise ValueError(f"{field} must be a canonical UUID4")
    value = event["version"]
    if not isinstance(value, str) or len(value) > 32 or not VERSION.fullmatch(value):
        raise ValueError("version must be major.minor.patch, at most 32 characters")
    return event


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def iso(timestamp):
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat()


class Store:
    """One SQLite transaction per event; launch IDs enforce concurrent deduplication."""

    def __init__(self, database, retention_days=90, clock=time.time):
        if type(retention_days) is not int or not 1 <= retention_days <= 3650:
            raise ValueError("retention_days must be from 1 through 3650")
        self.database = str(database)
        self.retention_days = retention_days
        self.clock = clock
        with self.connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                "CREATE TABLE IF NOT EXISTS launches ("
                "launch_id TEXT PRIMARY KEY, installation_id TEXT NOT NULL, "
                "version TEXT NOT NULL, received_at REAL NOT NULL)"
            )
            connection.execute("CREATE INDEX IF NOT EXISTS received ON launches(received_at)")
            connection.execute("CREATE INDEX IF NOT EXISTS installations ON launches(installation_id)")
        os.chmod(self.database, 0o600)

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.database, timeout=10)
        connection.execute("PRAGMA secure_delete=ON")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def prune(self, connection, now):
        connection.execute("DELETE FROM launches WHERE received_at < ?", (now - self.retention_days * 86400,))

    def record(self, event):
        validate_event(event)
        now = self.clock()
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self.prune(connection, now)
            existing = connection.execute(
                "SELECT installation_id, version FROM launches WHERE launch_id = ?",
                (event["launch_id"],),
            ).fetchone()
            if existing is not None:
                if existing != (event["installation_id"], event["version"]):
                    raise Conflict("launch_id already used")
                return False
            connection.execute(
                "INSERT INTO launches VALUES (?, ?, ?, ?)",
                (event["launch_id"], event["installation_id"], event["version"], now),
            )
        return True

    def summary(self):
        now = self.clock()
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self.prune(connection, now)
            total, installations = connection.execute(
                "SELECT COUNT(*), COUNT(DISTINCT installation_id) FROM launches"
            ).fetchone()
            versions = connection.execute(
                "SELECT version, COUNT(*), COUNT(DISTINCT installation_id) "
                "FROM launches GROUP BY version ORDER BY version"
            ).fetchall()
        return {
            "schema_version": 1, "generated_at": iso(now),
            "window_start": iso(now - self.retention_days * 86400),
            "retention_days": self.retention_days,
            "launches": total, "distinct_installations": installations,
            "by_version": [
                {"version": version, "launches": count, "distinct_installations": distinct}
                for version, count, distinct in versions
            ],
        }


class UsageServer(ThreadingHTTPServer):
    # Join bounded active requests during close before an operator rotates/removes
    # storage. A daemon worker must not write after shutdown has been reported.
    daemon_threads = False
    block_on_close = True

    def __init__(self, address, store, admin_token, max_connections=32, connection_deadline=10):
        if address[0] != "127.0.0.1":
            raise ValueError("bind to 127.0.0.1 behind an HTTPS reverse proxy")
        if not isinstance(admin_token, str) or len(admin_token.encode()) < 32:
            raise ValueError("TRACER_USAGE_ADMIN_TOKEN must contain at least 32 bytes")
        if type(connection_deadline) not in (int, float) or not 0 < connection_deadline <= 30:
            raise ValueError("connection_deadline must be positive and at most 30 seconds")
        self.store = store
        self.admin_token = admin_token
        self.connection_deadline = connection_deadline
        self.slots = threading.BoundedSemaphore(max_connections)
        super().__init__(address, Handler)

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            request.close()
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        def expire_connection():
            try:
                request.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

        deadline = threading.Timer(self.connection_deadline, expire_connection)
        deadline.daemon = True
        deadline.start()
        try:
            super().process_request_thread(request, client_address)
        finally:
            deadline.cancel()
            deadline.join()
            self.slots.release()

    def handle_error(self, request, client_address):
        # Avoid request/IP-bearing tracebacks. Monitor reverse-proxy 5xx metrics.
        return


class Handler(BaseHTTPRequestHandler):
    server_version = "TRACERUsage"
    sys_version = ""

    def setup(self):
        super().setup()
        self.connection.settimeout(5)

    def log_message(self, format, *args):
        # Never persist source IPs, URLs, identifiers, tokens, or request bodies.
        return

    def respond(self, status, body):
        payload = json.dumps(body, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(payload)
        self.close_connection = True

    def do_POST(self):
        if self.path != "/v1/launches":
            return self.respond(404, {"error": "not_found"})
        lengths = self.headers.get_all("Content-Length", [])
        if "Transfer-Encoding" in self.headers or len(lengths) != 1:
            return self.respond(400, {"error": "content_length_required"})
        if not re.fullmatch(r"[0-9]{1,6}", lengths[0]):
            return self.respond(400, {"error": "invalid_content_length"})
        length = int(lengths[0])
        if not 1 <= length <= MAX_BODY:
            return self.respond(413, {"error": "body_too_large"})
        if len(self.headers.get_all("Content-Type", [])) != 1 or self.headers.get_content_type() != "application/json":
            return self.respond(415, {"error": "application_json_required"})
        try:
            data = self.rfile.read(length)
            if len(data) != length:
                return self.respond(400, {"error": "incomplete_body"})
            event = json.loads(data.decode("utf-8"), object_pairs_hook=unique_object)
            created = self.server.store.record(event)
        except Conflict:
            return self.respond(409, {"error": "conflicting_launch_id"})
        except (UnicodeError, ValueError, RecursionError):
            return self.respond(400, {"error": "invalid_event"})
        except (TimeoutError, ConnectionError):
            return self.respond(408, {"error": "request_timeout"})
        except sqlite3.Error:
            return self.respond(503, {"error": "storage_unavailable"})
        return self.respond(202 if created else 200, {"accepted": True, "duplicate": not created})

    def do_GET(self):
        if self.path != "/v1/summary":
            return self.respond(404, {"error": "not_found"})
        expected = ("Bearer " + self.server.admin_token).encode("utf-8")
        supplied = self.headers.get("Authorization", "").encode("utf-8")
        if not hmac.compare_digest(supplied, expected):
            return self.respond(401, {"error": "unauthorized"})
        try:
            summary = self.server.store.summary()
        except sqlite3.Error:
            return self.respond(503, {"error": "storage_unavailable"})
        return self.respond(200, summary)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--retention-days", type=int, default=90)
    parser.add_argument("--prune", action="store_true", help="prune expired events and exit")
    args = parser.parse_args()
    token = os.environ.get("TRACER_USAGE_ADMIN_TOKEN", "")
    if len(token.encode()) < 32:
        parser.error("set TRACER_USAGE_ADMIN_TOKEN to a random secret of at least 32 bytes")
    os.umask(0o077)
    store = Store(args.database, args.retention_days)
    if args.prune:
        store.summary()
        return
    server = UsageServer(("127.0.0.1", args.port), store, token)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
