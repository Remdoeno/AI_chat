import http.client
import importlib.util
import pathlib
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


ROOT = pathlib.Path(__file__).resolve().parents[1]
PROXY_PATH = ROOT / "scripts" / "qwen_ip_proxy.py"

spec = importlib.util.spec_from_file_location("qwen_ip_proxy", PROXY_PATH)
qwen_ip_proxy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qwen_ip_proxy)


class SlowSseHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        return

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(b"data: one\n\n")
        self.wfile.flush()
        time.sleep(0.6)
        self.wfile.write(b"data: two\n\n")
        self.wfile.flush()


class QwenIpProxyTests(unittest.TestCase):
    def test_sse_body_is_forwarded_without_waiting_for_upstream_close(self):
        upstream = ThreadingHTTPServer(("127.0.0.1", 0), SlowSseHandler)
        upstream_thread = threading.Thread(target=upstream.serve_forever, daemon=True)
        upstream_thread.start()

        proxy = qwen_ip_proxy.ReusableThreadingHTTPServer(
            ("127.0.0.1", 0),
            qwen_ip_proxy.make_handler("127.0.0.1", upstream.server_port),
        )
        proxy_thread = threading.Thread(target=proxy.serve_forever, daemon=True)
        proxy_thread.start()

        try:
            conn = http.client.HTTPConnection("127.0.0.1", proxy.server_port, timeout=3)
            conn.request("GET", "/stream")
            response = conn.getresponse()
            start = time.monotonic()
            first_byte = response.read(1)
            elapsed = time.monotonic() - start
            conn.close()
        finally:
            proxy.shutdown()
            upstream.shutdown()
            proxy.server_close()
            upstream.server_close()

        self.assertEqual(b"d", first_byte)
        self.assertLess(elapsed, 0.3)


if __name__ == "__main__":
    unittest.main()
