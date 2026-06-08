import http.server
import json
import socket
import threading
import unittest

import httpx
import requests

from lod.middleware import (
    LODHTTPXAsyncTransport,
    LODHTTPXTransport,
    LODRequestsAdapter,
    LODValidationError,
    RequestValidator,
)


def get_free_port() -> int:
    """Returns a free local port."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class MockUpstreamHandler(http.server.BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        pass

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"message": "upstream_ok"}')

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length > 0 else b""
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body or b'{"message": "upstream_post_ok"}')


class TestRequestValidatorUnit(unittest.TestCase):

    def setUp(self):
        self.test_spec = {
            "openapi": "3.0.0",
            "info": {"title": "Test Middleware API", "version": "1.0.0"},
            "paths": {
                "/items/{id}": {
                    "get": {
                        "parameters": [
                            {
                                "name": "id",
                                "in": "path",
                                "required": True,
                                "schema": {"type": "integer"},
                            },
                            {
                                "name": "flag",
                                "in": "query",
                                "required": False,
                                "schema": {"type": "boolean"},
                            },
                        ]
                    }
                },
                "/items": {
                    "post": {
                        "requestBody": {
                            "required": True,
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "name": {"type": "string"},
                                            "count": {"type": "integer", "minimum": 1},
                                        },
                                        "required": ["name"],
                                    }
                                }
                            },
                        }
                    }
                },
            },
        }
        self.validator = RequestValidator(self.test_spec)

    def test_valid_get_request(self):
        # Should not raise exception
        self.validator.validate_request(
            method="GET",
            url="http://localhost/items/123?flag=true",
            headers={},
            body=b"",
        )

    def test_invalid_path_parameter_type(self):
        with self.assertRaises(LODValidationError) as cm:
            self.validator.validate_request(
                method="GET",
                url="http://localhost/items/abc",
                headers={},
                body=b"",
            )
        errors = cm.exception.errors
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]["location"], "path")
        self.assertEqual(errors[0]["parameter"], "id")
        self.assertIn("is not of type 'integer'", errors[0]["description"])

    def test_missing_required_request_body(self):
        with self.assertRaises(LODValidationError) as cm:
            self.validator.validate_request(
                method="POST",
                url="http://localhost/items",
                headers={},
                body=b"",
            )
        errors = cm.exception.errors
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]["location"], "body")
        self.assertEqual(errors[0]["parameter"], "requestBody")
        self.assertEqual(errors[0]["issue"], "missing_request_body")

    def test_invalid_request_body_schema(self):
        payload = json.dumps({"name": "Widget", "count": 0}).encode("utf-8")
        with self.assertRaises(LODValidationError) as cm:
            self.validator.validate_request(
                method="POST",
                url="http://localhost/items",
                headers={"Content-Type": "application/json"},
                body=payload,
            )
        errors = cm.exception.errors
        # count should be >= 1
        params = [e["parameter"] for e in errors]
        self.assertIn("count", params)


class TestMiddlewareIntegration(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # Start Mock Upstream Server
        cls.upstream_port = get_free_port()
        cls.upstream_server = http.server.ThreadingHTTPServer(
            ("localhost", cls.upstream_port), MockUpstreamHandler
        )
        cls.upstream_thread = threading.Thread(
            target=cls.upstream_server.serve_forever, daemon=True
        )
        cls.upstream_thread.start()

        cls.test_spec = {
            "openapi": "3.0.0",
            "info": {"title": "Test Integration API", "version": "1.0.0"},
            "paths": {
                "/users/{id}": {
                    "get": {
                        "parameters": [
                            {
                                "name": "id",
                                "in": "path",
                                "required": True,
                                "schema": {"type": "integer"},
                            }
                        ]
                    }
                },
                "/users": {
                    "post": {
                        "requestBody": {
                            "required": True,
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "username": {"type": "string"},
                                        },
                                        "required": ["username"],
                                    }
                                }
                            },
                        }
                    }
                },
            },
        }

    @classmethod
    def tearDownClass(cls):
        cls.upstream_server.shutdown()

    def test_requests_adapter_valid(self):
        session = requests.Session()
        adapter = LODRequestsAdapter(self.test_spec)
        session.mount(f"http://localhost:{self.upstream_port}", adapter)

        resp = session.get(f"http://localhost:{self.upstream_port}/users/123")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"message": "upstream_ok"})

    def test_requests_adapter_invalid(self):
        session = requests.Session()
        adapter = LODRequestsAdapter(self.test_spec)
        session.mount(f"http://localhost:{self.upstream_port}", adapter)

        with self.assertRaises(LODValidationError) as cm:
            session.get(f"http://localhost:{self.upstream_port}/users/abc")

        errors = cm.exception.errors
        self.assertEqual(errors[0]["location"], "path")
        self.assertEqual(errors[0]["parameter"], "id")

    def test_httpx_transport_valid(self):
        transport = LODHTTPXTransport(self.test_spec)
        with httpx.Client(transport=transport) as client:
            resp = client.get(f"http://localhost:{self.upstream_port}/users/555")
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp.json(), {"message": "upstream_ok"})

    def test_httpx_transport_invalid(self):
        transport = LODHTTPXTransport(self.test_spec)
        with httpx.Client(transport=transport) as client:
            with self.assertRaises(LODValidationError) as cm:
                client.post(
                    f"http://localhost:{self.upstream_port}/users",
                    json={"invalid_key": "val"},
                )
            errors = cm.exception.errors
            params = [e["parameter"] for e in errors]
            self.assertIn("username", params)

    async def _run_httpx_async_transport_valid_async(self):
        transport = LODHTTPXAsyncTransport(self.test_spec)
        async with httpx.AsyncClient(transport=transport) as client:
            resp = await client.get(f"http://localhost:{self.upstream_port}/users/777")
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp.json(), {"message": "upstream_ok"})

    async def _run_httpx_async_transport_invalid_async(self):
        transport = LODHTTPXAsyncTransport(self.test_spec)
        async with httpx.AsyncClient(transport=transport) as client:
            with self.assertRaises(LODValidationError) as cm:
                await client.get(f"http://localhost:{self.upstream_port}/users/xyz")
            errors = cm.exception.errors
            self.assertEqual(errors[0]["parameter"], "id")

    def test_httpx_async_transport_run(self):
        import asyncio
        asyncio.run(self._run_httpx_async_transport_valid_async())
        asyncio.run(self._run_httpx_async_transport_invalid_async())
        asyncio.run(self._run_httpx_async_transport_invalid_telemetry_async())

    def test_requests_adapter_invalid_telemetry(self):
        from unittest.mock import MagicMock
        session = requests.Session()
        adapter = LODRequestsAdapter(
            self.test_spec,
            telemetry_endpoint="http://localhost/dummy",
            telemetry_enabled=True,
        )
        adapter.telemetry_reporter.report_validation_error = MagicMock()
        session.mount(f"http://localhost:{self.upstream_port}", adapter)

        with self.assertRaises(LODValidationError):
            session.get(f"http://localhost:{self.upstream_port}/users/abc")

        adapter.telemetry_reporter.report_validation_error.assert_called_once()
        args, kwargs = adapter.telemetry_reporter.report_validation_error.call_args
        self.assertEqual(kwargs.get("method"), "GET")
        self.assertIn("/users/abc", kwargs.get("url"))
        self.assertEqual(kwargs.get("errors")[0]["parameter"], "id")

    def test_httpx_transport_invalid_telemetry(self):
        from unittest.mock import MagicMock
        transport = LODHTTPXTransport(
            self.test_spec,
            telemetry_endpoint="http://localhost/dummy",
            telemetry_enabled=True,
        )
        transport.telemetry_reporter.report_validation_error = MagicMock()
        with httpx.Client(transport=transport) as client:
            with self.assertRaises(LODValidationError):
                client.post(
                    f"http://localhost:{self.upstream_port}/users",
                    json={"invalid_key": "val"},
                )
            transport.telemetry_reporter.report_validation_error.assert_called_once()
            args, kwargs = transport.telemetry_reporter.report_validation_error.call_args
            self.assertEqual(kwargs.get("method"), "POST")
            self.assertEqual(kwargs.get("errors")[0]["location"], "body")

    async def _run_httpx_async_transport_invalid_telemetry_async(self):
        from unittest.mock import AsyncMock
        transport = LODHTTPXAsyncTransport(
            self.test_spec,
            telemetry_endpoint="http://localhost/dummy",
            telemetry_enabled=True,
        )
        transport.telemetry_reporter.report_validation_error = AsyncMock()
        async with httpx.AsyncClient(transport=transport) as client:
            with self.assertRaises(LODValidationError):
                await client.get(f"http://localhost:{self.upstream_port}/users/xyz")
            transport.telemetry_reporter.report_validation_error.assert_called_once()
            args, kwargs = transport.telemetry_reporter.report_validation_error.call_args
            self.assertEqual(kwargs.get("method"), "GET")
            self.assertEqual(kwargs.get("errors")[0]["parameter"], "id")


if __name__ == "__main__":
    unittest.main()
