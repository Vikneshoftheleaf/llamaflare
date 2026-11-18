from __future__ import annotations

import os
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from fastapi.testclient import TestClient

from model_server.proxy import app


class UpstreamHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        body = b'{"data":[]}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


class ProxyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.upstream = ThreadingHTTPServer(("127.0.0.1", 0), UpstreamHandler)
        self.upstream_thread = threading.Thread(target=self.upstream.serve_forever)
        self.upstream_thread.start()
        self.client = TestClient(app)
        self.environment = patch.dict(
            os.environ,
            {
                "MODEL_SERVER_API_KEY": "test-key",
                "MODEL_SERVER_UPSTREAM": f"http://127.0.0.1:{self.upstream.server_port}",
            },
        )
        self.environment.start()

    def tearDown(self) -> None:
        self.environment.stop()
        self.upstream.shutdown()
        self.upstream.server_close()
        self.upstream_thread.join()

    def test_requires_bearer_token(self) -> None:
        response = self.client.get("/v1/models")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.headers["www-authenticate"], "Bearer")

    def test_rejects_incorrect_bearer_token(self) -> None:
        response = self.client.get("/v1/models", headers={"Authorization": "Bearer wrong"})

        self.assertEqual(response.status_code, 401)

    def test_forwards_request_with_valid_bearer_token(self) -> None:
        response = self.client.get("/v1/models", headers={"Authorization": "Bearer test-key"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"data": []})


if __name__ == "__main__":
    unittest.main()
