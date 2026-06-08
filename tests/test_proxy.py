import unittest
import http.server
import threading
import urllib.request
import urllib.error
import json
import socket
import time

from lod.proxy import compile_openapi_paths, coerce_type, ValidationProxyHandler, start_proxy, build_proxy_app


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
        body = self.rfile.read(content_length)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)


class TestProxyUnit(unittest.TestCase):
    def test_compile_openapi_paths(self):
        spec = {
            "paths": {
                "/users": {},
                "/users/{id}": {},
                "/users/{userId}/posts/{postId}": {}
            }
        }
        compiled = compile_openapi_paths(spec)
        self.assertEqual(len(compiled), 3)

        # Match /users
        m1 = compiled[0]["pattern"].match("/users")
        self.assertIsNotNone(m1)
        self.assertEqual(m1.groupdict(), {})

        # Match /users/123
        m2 = compiled[1]["pattern"].match("/users/123")
        self.assertIsNotNone(m2)
        self.assertEqual(m2.groupdict(), {"id": "123"})

        # Match /users/abc/posts/456
        m3 = compiled[2]["pattern"].match("/users/abc/posts/456")
        self.assertIsNotNone(m3)
        self.assertEqual(m3.groupdict(), {"userId": "abc", "postId": "456"})

        # Mismatch
        self.assertIsNone(compiled[1]["pattern"].match("/users/123/posts"))

    def test_coerce_type(self):
        self.assertEqual(coerce_type("123", "integer"), 123)
        self.assertEqual(coerce_type("12.3", "number"), 12.3)
        self.assertEqual(coerce_type("true", "boolean"), True)
        self.assertEqual(coerce_type("false", "boolean"), False)
        self.assertEqual(coerce_type("1", "boolean"), True)
        self.assertEqual(coerce_type("0", "boolean"), False)
        self.assertEqual(coerce_type("abc", "integer"), "abc")  # fallback to raw string on failure
        self.assertEqual(coerce_type("abc", "string"), "abc")


class UvicornServerThread(threading.Thread):
    def __init__(self, app, host="localhost", port=8000):
        super().__init__(daemon=True)
        import uvicorn
        config = uvicorn.Config(app, host=host, port=port, log_level="warning")
        self.server = uvicorn.Server(config)

    def run(self):
        self.server.run()

    def shutdown(self):
        self.server.should_exit = True


class TestProxyIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # 1. Start Mock Upstream Server
        cls.upstream_port = get_free_port()
        cls.upstream_server = http.server.ThreadingHTTPServer(
            ("localhost", cls.upstream_port),
            MockUpstreamHandler
        )
        cls.upstream_thread = threading.Thread(target=cls.upstream_server.serve_forever, daemon=True)
        cls.upstream_thread.start()

        # 2. Setup OpenAPI Spec
        cls.test_spec = {
            "openapi": "3.0.0",
            "info": {"title": "Test Proxy API", "version": "1.0.0"},
            "paths": {
                "/users/{id}": {
                    "get": {
                        "parameters": [
                            {
                                "name": "id",
                                "in": "path",
                                "required": True,
                                "schema": {"type": "integer"}
                            },
                            {
                                "name": "verbose",
                                "in": "query",
                                "required": False,
                                "schema": {"type": "boolean"}
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
                                            "role": {"type": "string", "enum": ["admin", "user"]}
                                        },
                                        "required": ["username"]
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }

        # 3. Start Validation Proxy Server (Async FastAPI/Uvicorn mode)
        cls.proxy_port = get_free_port()
        cls.proxy_app = build_proxy_app(cls.test_spec, f"http://localhost:{cls.upstream_port}")
        cls.proxy_server_thread = UvicornServerThread(cls.proxy_app, "localhost", cls.proxy_port)
        cls.proxy_server_thread.start()
        time.sleep(0.5)  # Wait for uvicorn to startup

    @classmethod
    def tearDownClass(cls):
        cls.proxy_server_thread.shutdown()
        cls.upstream_server.shutdown()

    def test_proxy_forward_valid_get(self):
        # Valid path parameter 'id' (integer) and query 'verbose' (boolean)
        url = f"http://localhost:{self.proxy_port}/users/123?verbose=true"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(data["message"], "upstream_ok")

    def test_proxy_invalid_path_param_type(self):
        # 'id' should be integer, providing 'abc' (string)
        url = f"http://localhost:{self.proxy_port}/users/abc"
        req = urllib.request.Request(url)
        with self.assertRaises(urllib.error.HTTPError) as cm:
            urllib.request.urlopen(req)
        
        self.assertEqual(cm.exception.code, 422)
        body = json.loads(cm.exception.read().decode("utf-8"))
        self.assertEqual(body["status"], "error")
        self.assertEqual(len(body["errors"]), 1)
        self.assertEqual(body["errors"][0]["location"], "path")
        self.assertEqual(body["errors"][0]["parameter"], "id")
        self.assertIn("is not of type 'integer'", body["errors"][0]["description"])

    def test_proxy_missing_required_request_body(self):
        # POST /users requires requestBody
        url = f"http://localhost:{self.proxy_port}/users"
        req = urllib.request.Request(url, method="POST", headers={"Content-Type": "application/json"})
        with self.assertRaises(urllib.error.HTTPError) as cm:
            urllib.request.urlopen(req)
            
        self.assertEqual(cm.exception.code, 422)
        body = json.loads(cm.exception.read().decode("utf-8"))
        self.assertEqual(body["errors"][0]["location"], "body")
        self.assertEqual(body["errors"][0]["parameter"], "requestBody")
        self.assertEqual(body["errors"][0]["issue"], "missing_request_body")

    def test_proxy_invalid_request_body_schema(self):
        # POST /users body misses 'username' and has invalid 'role' enum
        url = f"http://localhost:{self.proxy_port}/users"
        payload = json.dumps({"role": "invalid_role"}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json", "Content-Length": str(len(payload))},
            method="POST"
        )
        with self.assertRaises(urllib.error.HTTPError) as cm:
            urllib.request.urlopen(req)
            
        self.assertEqual(cm.exception.code, 422)
        body = json.loads(cm.exception.read().decode("utf-8"))
        
        # Should catch multiple schema errors: missing username, invalid role enum
        errors = body["errors"]
        params = [e["parameter"] for e in errors]
        self.assertIn("username", params)
        self.assertIn("role", params)

    def test_proxy_forward_valid_post(self):
        url = f"http://localhost:{self.proxy_port}/users"
        payload = json.dumps({"username": "milad", "role": "admin"}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json", "Content-Length": str(len(payload))},
            method="POST"
        )
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(data["username"], "milad")
            self.assertEqual(data["role"], "admin")

    def test_proxy_endpoint_not_found(self):
        # Dynamic path /posts is not defined in spec
        url = f"http://localhost:{self.proxy_port}/posts"
        req = urllib.request.Request(url)
        with self.assertRaises(urllib.error.HTTPError) as cm:
            urllib.request.urlopen(req)
            
        self.assertEqual(cm.exception.code, 422)
        body = json.loads(cm.exception.read().decode("utf-8"))
        self.assertEqual(body["errors"][0]["issue"], "endpoint_not_found")


if __name__ == "__main__":
    unittest.main()
