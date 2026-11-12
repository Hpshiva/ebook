"""Free discovery sources: DuckDuckGo HTML search and manual username/URL import.

A search engine only surfaces a small, uneven sample of Instagram. This never
claims full coverage; every handle records which source found it.
"""
from __future__ import annotations

import re
import time
from urllib.parse import parse_qs, unquote, urlparse

import requests
from bs4 import BeautifulSoup

from .base import DiscoveryProvider, DiscoveryResult, Handle

UA = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}
RESERVED = {
    "p", "reel", "reels", "explore", "stories", "tv", "accounts", "about", "developer", "legal",
    "directory", "web", "challenge", "tags", "locations", "popular", "direct", "privacy", "terms",
    "session", "emails", "press", "api", "static",
}
IG_RE = re.compile(r"instagram\.com/([A-Za-z0-9_.]{1,30})(?:[/?#]|$)", re.I)
FOLLOWERS_RE = re.compile(r"([\d][\d.,]*)\s*([KkMm])?\+?\s+Followers", re.I)
EMAIL_MARKERS = ("@gmail.com", "@yahoo.com", "@outlook.com", "email")


def username_from_url(url: str) -> str | None:
    m = IG_RE.search(unquote(url or ""))
    if not m:
        return None
    name = m.group(1).lower().strip(".")
    return None if not name or name in RESERVED else name


def parse_followers(text: str) -> int | None:
    m = FOLLOWERS_RE.search(text or "")
    if not m:
        return None
    try:
        num = float(m.group(1).replace(",", ""))
    except ValueError:
        return None
    return int(num * {"k": 1_000, "m": 1_000_000}.get((m.group(2) or "").lower(), 1))


def parse_username_list(text: str) -> list[str]:
    """Accept pasted usernames, @handles or profile URLs (any separator)."""
    names: list[str] = []
    for raw in re.split(r"[\s,;]+", text or ""):
        raw = raw.strip()
        if not raw:
            continue
        name = username_from_url(raw) if "instagram.com" in raw.lower() else raw.lstrip("@").lower()
        if name and re.fullmatch(r"[a-z0-9_.]{1,30}", name):
            names.append(name)
    return list(dict.fromkeys(names))


def build_queries(params: dict) -> list[str]:
    niche = (params.get("niche") or "").strip()
    sub = (params.get("sub_niche") or "").strip()
    country = (params.get("country") or "").strip()
    terms = [t for t in (sub, niche) if t]
    queries = []
    for term in terms:
        extra = f' "{country}"' if country else ""
        for marker in EMAIL_MARKERS:
            queries.append(f'site:instagram.com "{term}" "{marker}"{extra}')
    return list(dict.fromkeys(queries))


def parse_ddg_html(html: str) -> tuple[list[tuple[str, str, str]], dict | None]:
    """Return ([(url, title, snippet)], next_page_form_data)."""
    soup = BeautifulSoup(html, "html.parser")
    rows = []
    for block in soup.select("div.result"):
        a = block.select_one("a.result__a")
        if not a:
            continue
        href = a.get("href", "")
        if "uddg=" in href:
            href = unquote(parse_qs(urlparse(href).query).get("uddg", [href])[0])
        snip = block.select_one(".result__snippet")
        rows.append((href, a.get_text(" ", strip=True), snip.get_text(" ", strip=True) if snip else ""))
    nxt = None
    for form in soup.select("form"):
        if form.select_one("input[type=submit][value=Next]"):
            nxt = {i.get("name"): i.get("value", "") for i in form.select("input[name]")}
            break
    return rows, nxt


class DuckDuckGoDiscovery(DiscoveryProvider):
    name = "duckduckgo"
    is_external = True  # free, but it is still an outside service

    def __init__(self, session: requests.Session | None = None, sleep=time.sleep, pages: int = 2, retries: int = 3):
        self.http = session or requests.Session()
        self.sleep = sleep
        self.pages = pages
        self.retries = retries

    def _post(self, data: dict) -> str | None:
        for attempt in range(self.retries):
            try:
                resp = self.http.post("https://html.duckduckgo.com/html/", data=data, headers=UA, timeout=20)
                if resp.status_code == 200:
                    return resp.text
            except requests.RequestException:
                pass
            self.sleep(2 ** attempt * 2)
        return None

    def discover(self, params: dict, limit: int) -> DiscoveryResult:
        out = DiscoveryResult()
        found: dict[str, Handle] = {}
        blocked = False
        for query in build_queries(params):
            if len(found) >= limit or blocked:
                break
            data: dict | None = {"q": query}
            for _ in range(self.pages):
                html = self._post(data)
                if html is None:
                    blocked = True
                    out.messages.append("DuckDuckGo blocked the automated search (rate limit or bot check). Showing what was found so far. "
                                        "Use Manual import for a dependable result.")
                    break
                rows, data = parse_ddg_html(html)
                for url, title, snippet in rows:
                    name = username_from_url(url)
                    if name and name not in found:
                        found[name] = Handle(name, "duckduckgo", title, snippet, parse_followers(f"{title} {snippet}"))
                if not data or len(found) >= limit:
                    break
                self.sleep(1.5)
            self.sleep(1.5)
        if not build_queries(params):
            out.messages.append("Enter a niche to search.")
        out.handles = list(found.values())[:limit]
        out.messages.append(
            f"DuckDuckGo found {len(out.handles)} profile(s). Search engines show only a sample of Instagram, not every account."
        )
        return out


class ManualDiscovery(DiscoveryProvider):
    name = "manual"

    def discover(self, params: dict, limit: int) -> DiscoveryResult:
        names = parse_username_list(params.get("usernames") or "")
        out = DiscoveryResult(handles=[Handle(n, "manual") for n in names[:limit]])
        if len(names) > limit:
            out.messages.append(f"Only the first {limit} of {len(names)} usernames were used (per-search limit).")
        if not names:
            out.messages.append("No valid Instagram usernames or profile URLs were found in the list.")
        return out
