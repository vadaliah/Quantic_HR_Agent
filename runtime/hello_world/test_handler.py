import json
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from handler import handle
from main import HelloWorldHandler


class HandleTests(unittest.TestCase):
    def test_returns_hello_world_without_prompt(self) -> None:
        self.assertEqual(
            handle({}),
            {"status": "ok", "message": "Hello World", "echo": ""},
        )

    def test_echoes_prompt_only(self) -> None:
        self.assertEqual(
            handle({"prompt": "ping"}),
            {"status": "ok", "message": "Hello World", "echo": "ping"},
        )


class HttpContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), HelloWorldHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        host, port = cls.server.server_address[:2]
        cls.base = f"http://{host}:{port}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()

    def test_ping(self) -> None:
        with urllib.request.urlopen(f"{self.base}/ping") as response:
            body = json.loads(response.read().decode("utf-8"))
        self.assertEqual(response.status, 200)
        self.assertEqual(body, {"status": "Healthy"})

    def test_invocations(self) -> None:
        request = urllib.request.Request(
            f"{self.base}/invocations",
            data=json.dumps({"prompt": "step1b"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request) as response:
            body = json.loads(response.read().decode("utf-8"))
        self.assertEqual(body["message"], "Hello World")
        self.assertEqual(body["echo"], "step1b")


if __name__ == "__main__":
    unittest.main()
