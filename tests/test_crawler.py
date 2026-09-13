import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from sitewatch.config import Site
from sitewatch.crawler import crawl

PAGES = {
    "/": b"""<html><head><title>Home</title>
        <link rel="preconnect" href="https://fonts.googleapis.com">
        <link rel="stylesheet" href="/style.css">
        <img src="/logo.png">
        </head><body>
        <a href="/about">About</a>
        <a href="/missing">Missing</a>
        <a href="mailto:hi@example.com">mail</a>
        </body></html>""",
    "/about": b"<html><head><title>About</title></head><body>ok <a href='/'>home</a></body></html>",
    "/style.css": b"body{}",
    "/logo.png": b"\x89PNG",
}


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in PAGES:
            self.send_response(200)
            ctype = "text/html" if self.path in ("/", "/about") else "application/octet-stream"
            self.send_header("Content-Type", ctype)
            self.end_headers()
            self.wfile.write(PAGES[self.path])
        else:
            self.send_response(404)
            self.end_headers()

    def do_HEAD(self):
        if self.path in PAGES:
            self.send_response(200)
            self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *a):
        pass


@pytest.fixture
def server():
    httpd = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_port}"
    httpd.shutdown()


def test_crawl_finds_all_pages(server):
    result = crawl(Site(name="Test", base_url=server), max_pages=10, max_depth=3)
    urls = {p.url for p in result.pages}
    assert f"{server}/" in urls
    assert f"{server}/about" in urls


def test_crawl_flags_broken_link(server):
    result = crawl(Site(name="Test", base_url=server), max_pages=10, max_depth=3)
    broken_targets = {i.target_url for i in result.broken_links}
    assert f"{server}/missing" in broken_targets


def test_crawl_ignores_preconnect_hints(server):
    result = crawl(Site(name="Test", base_url=server), max_pages=10, max_depth=3)
    assert not any("fonts.googleapis.com" in i.target_url for i in result.issues)


def test_crawl_checks_stylesheet_asset(server):
    result = crawl(Site(name="Test", base_url=server), max_pages=10, max_depth=3)
    # style.css and logo.png both resolve fine -- no asset issues expected
    assert result.broken_assets == []


def test_crawl_stays_under_max_pages(server):
    result = crawl(Site(name="Test", base_url=server), max_pages=1, max_depth=3)
    assert len(result.pages) == 1
