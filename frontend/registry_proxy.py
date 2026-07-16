"""本地 npm registry 代理：绕过 Node.js getaddrinfo 损坏问题.

原理：Node.js 的 DNS 解析 (getaddrinfo) 因 Winsock LSP 损坏而失败，
但 Python 的网络栈正常。本脚本在 localhost 启动 HTTP 代理，
将所有请求转发到 https://registry.npmmirror.com，
并重写 tarball URL 指向 localhost，让 npm 全程无需 DNS 解析。

用法：
    python registry_proxy.py          # 启动代理 (端口 8080)
    # 另一个终端：
    npm install --registry=http://127.0.0.1:8080
"""
from __future__ import annotations

import http.server
import json
import re
import socketserver
import sys
import urllib.error
import urllib.request

UPSTREAM = "https://registry.npmmirror.com"
LOCAL = "http://127.0.0.1:8080"
PORT = 8080

# 匹配 tarball URL 中的 registry 域名
_TARBALL_RE = re.compile(rb'"tarball":\s*"(?:https?://[^/]+)?(/[^"]+)"')


def _rewrite_tarball_urls(body: bytes) -> bytes:
    """将 metadata JSON 里的 tarball URL 重写为 localhost.

    npm 会直接用 dist.tarball 的 URL 下载包。如果不重写，
    npm 会尝试 DNS 解析 registry 域名并失败。
    重写后所有 tarball 下载也走本代理。
    """
    return _TARBALL_RE.sub(rb'"tarball": "' + LOCAL.encode() + rb'\1"', body)


class RegistryProxy(http.server.BaseHTTPRequestHandler):
    """将所有 GET/POST 请求透明转发到上游 registry，并重写 tarball URL."""

    def _proxy(self, method: str) -> None:
        path = self.path
        upstream_url = f"{UPSTREAM}{path}"

        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length > 0 else None

        req = urllib.request.Request(upstream_url, data=body, method=method)
        for key in ("Accept", "Accept-Encoding", "Content-Type", "User-Agent", "npm-in-ci"):
            val = self.headers.get(key)
            if val:
                req.add_header(key, val)

        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                status = resp.status
                resp_body = resp.read()
                content_type = resp.headers.get("Content-Type", "")

                # JSON metadata 响应：重写 tarball URL
                if "json" in content_type and b'"tarball"' in resp_body:
                    resp_body = _rewrite_tarball_urls(resp_body)

                self.send_response(status)
                for key, val in resp.getheaders():
                    if key.lower() in ("transfer-encoding", "content-encoding", "content-length"):
                        continue
                    self.send_header(key, val)
                self.send_header("Content-Length", str(len(resp_body)))
                self.end_headers()
                self.wfile.write(resp_body)
        except urllib.error.HTTPError as e:
            resp_body = e.read()
            self.send_response(e.code)
            self.send_header("Content-Length", str(len(resp_body)))
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(resp_body)
        except Exception as e:
            msg = json.dumps({"error": f"proxy error: {e}"}).encode()
            self.send_response(502)
            self.send_header("Content-Length", str(len(msg)))
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(msg)

    def do_GET(self) -> None:
        self._proxy("GET")

    def do_POST(self) -> None:
        self._proxy("POST")

    def log_message(self, format: str, *args) -> None:
        sys.stderr.write(f"[proxy] {format % args}\n")
        sys.stderr.flush()


class ThreadingHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def main() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", PORT), RegistryProxy)
    print(f"[registry_proxy] 监听 http://127.0.0.1:{PORT}")
    print(f"[registry_proxy] 上游: {UPSTREAM}")
    print(f"[registry_proxy] 在另一个终端运行:")
    print(f"  npm install --registry=http://127.0.0.1:{PORT}")
    print(f"[registry_proxy] Ctrl+C 停止")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[registry_proxy] 已停止")
        server.shutdown()


if __name__ == "__main__":
    main()
