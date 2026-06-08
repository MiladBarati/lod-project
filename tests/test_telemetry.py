import asyncio
import http.server
import json
import os
import socket
import threading
import time
import unittest

from lod.telemetry import (
    AsyncTelemetryReporter,
    SyncTelemetryReporter,
    resolve_telemetry_config,
    sanitize_url,
)


def get_free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class MockTelemetryHandler(http.server.BaseHTTPRequestHandler):
    received_requests = []

    def log_message(self, format, *args):
        pass

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length > 0 else b""
        self.received_requests.append({
            "path": self.path,
            "headers": dict(self.headers),
            "body": json.loads(body.decode("utf-8"))
        })
        self.send_response(200)
        self.end_headers()


class TestTelemetry(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.port = get_free_port()
        cls.server = http.server.HTTPServer(("localhost", cls.port), MockTelemetryHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        MockTelemetryHandler.received_requests.clear()

    def test_sanitize_url(self):
        self.assertEqual(
            sanitize_url("http://api.com/users?name=john&key=123"),
            "http://api.com/users?name=%5BREDACTED%5D&key=%5BREDACTED%5D"
        )
        self.assertEqual(sanitize_url("http://api.com/users"), "http://api.com/users")

    def test_resolve_telemetry_config(self):
        # Default fallback
        os.environ.pop("LOD_TELEMETRY_ENDPOINT", None)
        os.environ.pop("LOD_TELEMETRY_API_KEY", None)
        os.environ.pop("LOD_TELEMETRY_ENABLED", None)
        endpoint, api_key, enabled = resolve_telemetry_config()
        self.assertIsNone(endpoint)
        self.assertIsNone(api_key)
        self.assertTrue(enabled)

        # Env vars
        os.environ["LOD_TELEMETRY_ENDPOINT"] = "http://env-endpoint"
        os.environ["LOD_TELEMETRY_API_KEY"] = "env-key"
        os.environ["LOD_TELEMETRY_ENABLED"] = "false"
        endpoint, api_key, enabled = resolve_telemetry_config()
        self.assertEqual(endpoint, "http://env-endpoint")
        self.assertEqual(api_key, "env-key")
        self.assertFalse(enabled)

        # Override params
        endpoint, api_key, enabled = resolve_telemetry_config("http://param-endpoint", "param-key", True)
        self.assertEqual(endpoint, "http://param-endpoint")
        self.assertEqual(api_key, "param-key")
        self.assertTrue(enabled)

        # Cleanup
        os.environ.pop("LOD_TELEMETRY_ENDPOINT", None)
        os.environ.pop("LOD_TELEMETRY_API_KEY", None)
        os.environ.pop("LOD_TELEMETRY_ENABLED", None)

    def test_sync_telemetry_reporter(self):
        reporter = SyncTelemetryReporter(
            endpoint=f"http://localhost:{self.port}/telemetry",
            api_key="test_api_key",
            enabled=True
        )
        reporter.report_validation_error(
            method="POST",
            url="http://api.com/users?secret=abc",
            errors=[{"location": "body", "parameter": "name", "issue": "required"}]
        )
        time.sleep(0.5)
        reporter.stop()

        self.assertEqual(len(MockTelemetryHandler.received_requests), 1)
        req = MockTelemetryHandler.received_requests[0]
        self.assertEqual(req["path"], "/telemetry")
        self.assertEqual(req["headers"].get("Authorization"), "Bearer test_api_key")
        self.assertEqual(req["body"]["method"], "POST")
        self.assertEqual(req["body"]["url"], "http://api.com/users?secret=%5BREDACTED%5D")
        self.assertEqual(len(req["body"]["errors"]), 1)
        self.assertEqual(req["body"]["errors"][0]["parameter"], "name")

    def test_async_telemetry_reporter(self):
        async def run_async_test():
            reporter = AsyncTelemetryReporter(
                endpoint=f"http://localhost:{self.port}/telemetry",
                api_key="async_test_key",
                enabled=True
            )
            await reporter.report_validation_error(
                method="GET",
                url="http://api.com/items?q=python",
                errors=[{"location": "path", "parameter": "id", "issue": "invalid_type"}]
            )
            await asyncio.sleep(0.5)
            await reporter.stop()

        asyncio.run(run_async_test())

        self.assertEqual(len(MockTelemetryHandler.received_requests), 1)
        req = MockTelemetryHandler.received_requests[0]
        self.assertEqual(req["path"], "/telemetry")
        self.assertEqual(req["headers"].get("Authorization"), "Bearer async_test_key")
        self.assertEqual(req["body"]["method"], "GET")
        self.assertEqual(req["body"]["url"], "http://api.com/items?q=%5BREDACTED%5D")
        self.assertEqual(len(req["body"]["errors"]), 1)
        self.assertEqual(req["body"]["errors"][0]["parameter"], "id")

    def test_graceful_degradation(self):
        reporter = SyncTelemetryReporter(
            endpoint="http://localhost:12345/nonexistent",
            enabled=True
        )
        # Should not raise exception
        reporter.report_validation_error("GET", "http://api.com", [])
        time.sleep(0.2)
        reporter.stop()


if __name__ == "__main__":
    unittest.main()
