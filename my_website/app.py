
import ipaddress
import re
import socket
from urllib.parse import urljoin, urlparse, quote

import requests
from flask import Flask, Response, abort, render_template, request

app = Flask(__name__)

HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "content-encoding",
    "content-length",
    "host",
}


def is_blocked_host(hostname: str) -> bool:
    if not hostname:
        return True
    name = hostname.lower()
    if name in {"localhost"} or name.endswith(".local"):
        return True
    try:
        infos = socket.getaddrinfo(name, None)
    except socket.gaierror:
        return True
    for info in infos:
        ip_str = info[4][0]
        ip = ipaddress.ip_address(ip_str)
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            return True
    return False


def rewrite_html(html: str, base_url: str) -> str:
    def proxied(abs_url: str) -> str:
        return "/proxy?url=" + quote(abs_url, safe="")

    attr_pattern = re.compile(r"""(?P<attr>\b(?:href|src|action)\s*=\s*)(?P<q>["'])(?P<url>.*?)(?P=q)""", re.IGNORECASE)
    css_url_pattern = re.compile(r"""url\((?P<q>["']?)(?P<url>[^"')]+)(?P=q)\)""", re.IGNORECASE)

    def replace_attr(match: re.Match) -> str:
        raw = match.group("url").strip()
        if not raw or raw.startswith(("data:", "javascript:", "mailto:", "#")):
            return match.group(0)
        absolute = urljoin(base_url, raw)
        return f'{match.group("attr")}{match.group("q")}{proxied(absolute)}{match.group("q")}'

    def replace_css_url(match: re.Match) -> str:
        raw = match.group("url").strip()
        if not raw or raw.startswith(("data:", "#")):
            return match.group(0)
        absolute = urljoin(base_url, raw)
        q = match.group("q") or ""
        return f"url({q}{proxied(absolute)}{q})"

    html = attr_pattern.sub(replace_attr, html)
    html = css_url_pattern.sub(replace_css_url, html)
    return html


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/about")
def about():
    return """
    <h1>このサイトについて</h1>
    <p>PythonとFlaskで作ったサイトです。</p>
    <a href="/">トップに戻る</a>
    """


@app.route("/proxy")
def proxy():
    target = request.args.get("url", "").strip()
    if not target:
        abort(400, "url parameter is required")

    parsed = urlparse(target)
    if parsed.scheme not in {"http", "https"}:
        abort(400, "Only http/https URLs are allowed")
    if is_blocked_host(parsed.hostname or ""):
        abort(403, "Target host is not allowed")

    headers = {
        "User-Agent": request.headers.get("User-Agent", "Mozilla/5.0"),
        "Accept": request.headers.get("Accept", "*/*"),
        "Accept-Language": request.headers.get("Accept-Language", "ja,en-US;q=0.9,en;q=0.8"),
    }

    try:
        upstream = requests.get(target, headers=headers, stream=True, timeout=15, allow_redirects=True)
    except requests.RequestException as e:
        abort(502, f"Upstream request failed: {e}")

    content_type = upstream.headers.get("Content-Type", "application/octet-stream")
    resp_headers = {}
    for k, v in upstream.headers.items():
        if k.lower() in HOP_BY_HOP_HEADERS:
            continue
        if k.lower() == "set-cookie":
            continue
        resp_headers[k] = v

    if "text/html" in content_type.lower():
        charset = upstream.encoding or "utf-8"
        body = upstream.content.decode(charset, errors="replace")
        body = rewrite_html(body, upstream.url)
        return Response(body, status=upstream.status_code, headers=resp_headers, content_type=content_type)

    return Response(upstream.content, status=upstream.status_code, headers=resp_headers, content_type=content_type)


if __name__ == "__main__":
    app.run(debug=True)
