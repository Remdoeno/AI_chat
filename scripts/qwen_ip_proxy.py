#!/usr/bin/env python3
import argparse
import http.client
import os
import signal
import socket
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}


def response_read_size(response) -> int:
    content_type = (response.getheader("Content-Type") or "").lower()
    if "text/event-stream" in content_type:
        return 1
    return 8192


class ReusableThreadingHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def make_handler(upstream_host: str, upstream_port: int):
    class ProxyHandler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt: str, *args):
            sys.stderr.write(
                "%s - - [%s] %s\n"
                % (self.client_address[0], self.log_date_time_string(), fmt % args)
            )

        def do_GET(self):
            self._proxy()

        def do_POST(self):
            self._proxy()

        def do_PATCH(self):
            self._proxy()

        def do_DELETE(self):
            self._proxy()

        def do_OPTIONS(self):
            self._proxy()

        def _proxy(self):
            body = None
            content_length = self.headers.get("Content-Length")
            if content_length:
                body = self.rfile.read(int(content_length))

            headers = {}
            for key, value in self.headers.items():
                lowered = key.lower()
                if lowered in HOP_BY_HOP_HEADERS:
                    continue
                if lowered in {"x-forwarded-for", "x-real-ip", "forwarded"}:
                    continue
                headers[key] = value

            client_ip = self.client_address[0]
            headers["Host"] = f"{upstream_host}:{upstream_port}"
            headers["X-Forwarded-For"] = client_ip
            headers["X-Real-IP"] = client_ip
            headers["Forwarded"] = f"for={client_ip}"
            headers["Connection"] = "close"

            conn = http.client.HTTPConnection(upstream_host, upstream_port, timeout=1200)
            try:
                conn.request(self.command, self.path, body=body, headers=headers)
                response = conn.getresponse()
                self.send_response(response.status, response.reason)
                for key, value in response.getheaders():
                    if key.lower() in HOP_BY_HOP_HEADERS:
                        continue
                    self.send_header(key, value)
                self.send_header("Connection", "close")
                self.end_headers()

                read_size = response_read_size(response)
                while True:
                    chunk = response.read(read_size)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    self.wfile.flush()
            finally:
                conn.close()

    return ProxyHandler


def serve_one(bind_host: str, bind_port: int, upstream_host: str, upstream_port: int):
    server = ReusableThreadingHTTPServer(
        (bind_host, bind_port),
        make_handler(upstream_host, upstream_port),
    )
    sys.stderr.write(
        f"qwen_ip_proxy listening on {bind_host}:{bind_port} -> "
        f"{upstream_host}:{upstream_port}\n"
    )
    server.serve_forever()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bind-hosts", required=True)
    parser.add_argument("--bind-port", required=True, type=int)
    parser.add_argument("--upstream-host", default="127.0.0.1")
    parser.add_argument("--upstream-port", required=True, type=int)
    parser.add_argument("--daemon", action="store_true")
    parser.add_argument("--pid-file", default="")
    parser.add_argument("--log-file", default="")
    args = parser.parse_args()

    if args.daemon:
        daemonize(args.pid_file, args.log_file)

    stop = threading.Event()

    def handle_signal(_signum, _frame):
        stop.set()

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    threads = []
    for raw_host in args.bind_hosts.split(","):
        bind_host = raw_host.strip()
        if not bind_host:
            continue
        thread = threading.Thread(
            target=serve_one,
            args=(bind_host, args.bind_port, args.upstream_host, args.upstream_port),
            daemon=False,
        )
        thread.start()
        threads.append(thread)

    if not threads:
        raise SystemExit("no bind hosts configured")

    try:
        while not stop.wait(1):
            if not any(thread.is_alive() for thread in threads):
                raise SystemExit("all proxy listeners exited")
    finally:
        # ThreadingHTTPServer has no shared handle here; process exit closes sockets.
        pass


def daemonize(pid_file: str, log_file: str):
    if os.fork() > 0:
        os._exit(0)
    os.setsid()
    if os.fork() > 0:
        os._exit(0)

    os.chdir("/")
    os.umask(0)

    stdin = open(os.devnull, "r")
    if log_file:
        os.makedirs(os.path.dirname(os.path.abspath(log_file)), exist_ok=True)
        stdout = open(log_file, "a", buffering=1)
    else:
        stdout = open(os.devnull, "a")
    os.dup2(stdin.fileno(), sys.stdin.fileno())
    os.dup2(stdout.fileno(), sys.stdout.fileno())
    os.dup2(stdout.fileno(), sys.stderr.fileno())

    if pid_file:
        os.makedirs(os.path.dirname(os.path.abspath(pid_file)), exist_ok=True)
        with open(pid_file, "w") as handle:
            handle.write(f"{os.getpid()}\n")


if __name__ == "__main__":
    try:
        main()
    except OSError as exc:
        sys.stderr.write(f"qwen_ip_proxy failed: {exc}\n")
        raise
