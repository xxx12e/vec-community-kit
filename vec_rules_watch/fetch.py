"""Polite HTTP GET with the standard library: one User-Agent naming the repository, a pause between requests to the
same host, a timeout, one retry on a timeout / 429 / 5xx, a size cap, and robots.txt respected for the organisers'
hosts. A failure never raises: it comes back as a FetchResult with a short, stable error string ("HTTP 503",
"timeout", ...), so a page that is down for a day is recorded, not fatal.

The GitHub token (GITHUB_TOKEN in the Action) is sent to api.github.com only, never to any other host.
"""
from __future__ import annotations

import os
import socket
import time
import urllib.error
import urllib.request
import urllib.robotparser
from dataclasses import dataclass, field
from urllib.parse import urlsplit

MAX_BYTES = 8 * 1024 * 1024
TOKEN_HOSTS = {"api.github.com"}


@dataclass
class FetchResult:
    url: str
    status: int = 0
    body: bytes = b""
    error: str = ""
    headers: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.error


def _stable_error(exc) -> str:
    if isinstance(exc, urllib.error.HTTPError):
        return f"HTTP {exc.code}"
    if isinstance(exc, (socket.timeout, TimeoutError)):
        return "timeout"
    if isinstance(exc, urllib.error.URLError):
        reason = exc.reason
        if isinstance(reason, (socket.timeout, TimeoutError)):
            return "timeout"
        if isinstance(reason, socket.gaierror):
            return "DNS lookup failed"
        return "connection error: " + type(reason).__name__
    return "error: " + type(exc).__name__


def _looks_like_challenge(status: int, headers: dict, body: bytes) -> bool:
    if (headers.get("cf-mitigated") or "").lower() == "challenge":
        return True
    head = body[:4096].lower()
    return status in (403, 429, 503) and (b"just a moment" in head or b"challenge-platform" in head)


class Fetcher:
    """fetch(url) -> FetchResult. Tests replace this object with a stub that has the same method."""

    def __init__(self, user_agent: str, delay: float = 1.5, timeout: float = 30.0, retries: int = 1,
                 retry_wait: float = 10.0, robots_hosts=(), token_env: str = "GITHUB_TOKEN"):
        self.user_agent = user_agent
        self.delay = delay
        self.timeout = timeout
        self.retries = retries
        self.retry_wait = retry_wait
        self.robots_hosts = set(robots_hosts)
        self.token_env = token_env
        self._last: dict = {}
        self._robots: dict = {}
        self.requests = 0

    def _headers_for(self, url: str) -> dict:
        h = {"User-Agent": self.user_agent, "Accept": "*/*"}
        host = urlsplit(url).hostname or ""
        token = os.environ.get(self.token_env, "")
        if host in TOKEN_HOSTS:
            h["Accept"] = "application/vnd.github+json"
            if token:
                h["Authorization"] = f"Bearer {token}"
        return h

    def _pause(self, host: str):
        last = self._last.get(host)
        if last is not None and self.delay > 0:
            wait = self.delay - (time.monotonic() - last)
            if wait > 0:
                time.sleep(wait)
        self._last[host] = time.monotonic()

    def _raw_get(self, url: str) -> FetchResult:
        host = urlsplit(url).hostname or ""
        self._pause(host)
        self.requests += 1
        req = urllib.request.Request(url, headers=self._headers_for(url))
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = resp.read(MAX_BYTES + 1)
                headers = {k.lower(): v for k, v in resp.headers.items()}
                if len(body) > MAX_BYTES:
                    return FetchResult(url, resp.status, b"", f"response larger than {MAX_BYTES} bytes", headers)
                if _looks_like_challenge(resp.status, headers, body):
                    return FetchResult(url, resp.status, b"", "blocked by a bot challenge", headers)
                return FetchResult(url, resp.status, body, "", headers)
        except urllib.error.HTTPError as exc:
            headers = {k.lower(): v for k, v in (exc.headers or {}).items()}
            try:
                body = exc.read(4096)
            except Exception:  # noqa: BLE001
                body = b""
            if _looks_like_challenge(exc.code, headers, body):
                return FetchResult(url, exc.code, b"", "blocked by a bot challenge", headers)
            return FetchResult(url, exc.code, b"", _stable_error(exc), headers)
        except Exception as exc:  # noqa: BLE001 - every network failure becomes a recorded error
            return FetchResult(url, 0, b"", _stable_error(exc))

    def _allowed(self, url: str) -> bool:
        parts = urlsplit(url)
        host = parts.hostname or ""
        if host not in self.robots_hosts:
            return True
        if host not in self._robots:
            rp = urllib.robotparser.RobotFileParser()
            res = self._raw_get(f"{parts.scheme}://{parts.netloc}/robots.txt")
            if res.ok:
                rp.parse(res.body.decode("utf-8", "replace").splitlines())
            elif 400 <= res.status < 500:
                rp.parse([])                       # no robots.txt: everything allowed
            else:
                rp = None                          # robots.txt unreachable: do not guess, allow and move on
            self._robots[host] = rp
        rp = self._robots[host]
        return True if rp is None else rp.can_fetch(self.user_agent, url)

    def fetch(self, url: str) -> FetchResult:
        if not self._allowed(url):
            return FetchResult(url, 0, b"", "disallowed by robots.txt")
        res = self._raw_get(url)
        tries = 0
        while not res.ok and tries < self.retries and (res.status == 0 or res.status == 429 or res.status >= 500):
            tries += 1
            if self.retry_wait > 0:
                time.sleep(self.retry_wait)
            res = self._raw_get(url)
        return res
