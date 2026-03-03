#!/usr/bin/env python3
"""Medium.com article search and scraper."""

import argparse
import json
import re
import sys
import time
import urllib.parse
from email.utils import parsedate_to_datetime
from pathlib import Path

from bs4 import BeautifulSoup
from curl_cffi import requests as cffi
from playwright.sync_api import sync_playwright

# ── Paths ─────────────────────────────────────────────────────────────────────

MEDIUM_HOME = Path.home() / ".medium"
STORAGE_PATH = MEDIUM_HOME / "storage_state.json"


# ── Auth helpers ──────────────────────────────────────────────────────────────

def load_cookies() -> dict[str, str]:
    """Load Medium cookies from Playwright storage state."""
    if not STORAGE_PATH.exists():
        print("Not logged in. Run:  medium.py login", file=sys.stderr)
        sys.exit(1)
    state = json.loads(STORAGE_PATH.read_text())
    cookies = {}
    for c in state.get("cookies", []):
        domain = c.get("domain", "")
        if "medium.com" in domain or "cloudflare" in domain.lower():
            name = c.get("name")
            if name:
                cookies[name] = c.get("value", "")
    if not cookies:
        print("No cookies found. Re-run:  medium.py login", file=sys.stderr)
        sys.exit(1)
    return cookies


# ── HTTP fetch ────────────────────────────────────────────────────────────────

def _get(url: str, cookies: dict[str, str]) -> str:
    """GET url impersonating Chrome to bypass Cloudflare."""
    resp = cffi.get(url, cookies=cookies, impersonate="chrome110",
                    allow_redirects=True, timeout=30)
    resp.raise_for_status()
    return resp.text


# ── Apollo State parsing ──────────────────────────────────────────────────────

def _parse_apollo_state(html: str) -> list[dict]:
    """Extract article list from window.__APOLLO_STATE__ embedded in page HTML."""
    scripts = re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL)
    apollo_raw = next((s for s in scripts if 'window.__APOLLO_STATE__' in s), None)
    if not apollo_raw:
        return []

    json_str = apollo_raw.strip()
    json_str = json_str[json_str.index('{'):].rstrip('; \n')
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError:
        return []

    posts = {k: v for k, v in data.items() if k.startswith('Post:') and v.get('title')}
    users = {k: v for k, v in data.items() if k.startswith('User:')}

    results = []
    for post in posts.values():
        ref = post.get("creator", {}).get("__ref", "")
        user = users.get(ref, {})
        url = post.get("mediumUrl", "")
        if not url:
            username = user.get("username", "")
            slug = post.get("uniqueSlug", "")
            url = f"https://medium.com/@{username}/{slug}" if username and slug else ""
        results.append({
            "title":        post.get("title", ""),
            "url":          url,
            "author":       user.get("name", user.get("username", "")),
            "username":     user.get("username", ""),
            "date":         _fmt_date(post.get("firstPublishedAt", 0)),
            "reading_time": round(post.get("readingTime", 0)),
            "claps":        post.get("clapCount", 0),
        })
    return results


def _fmt_date(ms: int) -> str:
    if not ms:
        return ""
    return time.strftime("%Y-%m-%d", time.localtime(ms / 1000))


# ── RSS parsing (tag / author / publication) ──────────────────────────────────

def _parse_rss(xml: str) -> list[dict]:
    """Parse Medium RSS feed, return list of article dicts."""
    items = re.findall(r'<item>(.*?)</item>', xml, re.DOTALL)
    results = []
    for item in items:
        def _cdata(tag: str) -> str:
            m = re.search(rf'<{tag}><!\[CDATA\[(.*?)\]\]></{tag}>', item, re.DOTALL)
            return m.group(1).strip() if m else ""
        def _text(tag: str) -> str:
            m = re.search(rf'<{tag}>(.*?)</{tag}>', item)
            return m.group(1).strip() if m else ""

        link = _text("link")
        # Clean tracking params from URL
        link = re.sub(r'\?source=rss.*$', '', link)

        pub_date = _text("pubDate")
        date = ""
        if pub_date:
            try:
                date = parsedate_to_datetime(pub_date).strftime("%Y-%m-%d")
            except Exception:
                pass

        results.append({
            "title":        _cdata("title"),
            "url":          link,
            "author":       _cdata("dc:creator"),
            "username":     "",
            "date":         date,
            "reading_time": 0,
            "claps":        0,
        })
    return results


def _rss_listing(rss_url: str, n: int) -> list[dict]:
    cookies = load_cookies()
    xml = _get(rss_url, cookies)
    return _parse_rss(xml)[:n]


# ── Listing commands ──────────────────────────────────────────────────────────

def cmd_search(query: str, n: int) -> list[dict]:
    cookies = load_cookies()
    q = urllib.parse.quote_plus(query)
    html = _get(f"https://medium.com/search?q={q}", cookies)
    return _parse_apollo_state(html)[:n]


def cmd_tag(tag: str, n: int) -> list[dict]:
    return _rss_listing(f"https://medium.com/feed/tag/{tag}", n)


def cmd_author(username: str, n: int) -> list[dict]:
    username = username.lstrip("@")
    return _rss_listing(f"https://medium.com/feed/@{username}", n)


def cmd_publication(slug: str, n: int) -> list[dict]:
    return _rss_listing(f"https://medium.com/feed/{slug}", n)


def print_listing(results: list[dict]) -> None:
    if not results:
        print("Keine Ergebnisse gefunden.")
        return
    for i, r in enumerate(results, 1):
        claps = f"{r['claps']:,}" if r["claps"] else "—"
        print(f"{i:2}. {r['title']}")
        print(f"    URL:    {r['url']}")
        print(f"    Autor:  {r['author']}")
        print(f"    Datum:  {r['date']}  •  {r['reading_time']} min  •  {claps} claps")
        print()


# ── Article read ──────────────────────────────────────────────────────────────

def cmd_read(url: str) -> dict:
    """Fetch and parse a Medium article. Returns dict with title, author, text."""
    cookies = load_cookies()
    html = _get(url, cookies)
    soup = BeautifulSoup(html, "html.parser")

    # Title
    title_tag = soup.find("h1")
    title = title_tag.get_text(strip=True) if title_tag else ""
    if not title:
        og = soup.find("meta", property="og:title")
        title = og["content"] if og else ""

    # Author
    author = ""
    author_meta = soup.find("meta", attrs={"name": "author"})
    if author_meta:
        author = author_meta.get("content", "")
    if not author:
        a_tag = soup.find("a", attrs={"data-testid": "authorName"})
        if a_tag:
            author = a_tag.get_text(strip=True)

    # Publication date
    date = ""
    time_tag = soup.find("meta", property="article:published_time")
    if time_tag:
        date = time_tag.get("content", "")[:10]

    # Body text
    article_tag = soup.find("article")
    paragraphs = []
    if article_tag:
        for tag in article_tag.find_all(["h1", "h2", "h3", "h4", "p", "pre", "li"]):
            text = tag.get_text(strip=True)
            if text:
                if tag.name in ("h1", "h2", "h3", "h4"):
                    paragraphs.append(f"\n## {text}\n")
                elif tag.name == "pre":
                    paragraphs.append(f"\n```\n{text}\n```\n")
                else:
                    paragraphs.append(text)

    return {
        "title":  title,
        "author": author,
        "date":   date,
        "url":    url,
        "text":   "\n\n".join(paragraphs),
    }


def print_article(article: dict) -> None:
    print(f"# {article['title']}")
    print(f"Autor: {article['author']}  •  {article['date']}")
    print(f"URL:   {article['url']}")
    print()
    print(article["text"])


# ── Login ─────────────────────────────────────────────────────────────────────

def cmd_login() -> None:
    """Open browser, wait for user to log in, save cookies."""
    MEDIUM_HOME.mkdir(parents=True, exist_ok=True, mode=0o700)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto("https://medium.com/m/signin")
        print("Log in to Medium in the browser window, then press Enter here…")
        input()
        context.storage_state(path=str(STORAGE_PATH))
        browser.close()

    STORAGE_PATH.chmod(0o600)
    print(f"Cookies saved to {STORAGE_PATH}")


# ── CLI entry ─────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="medium.py",
        description="Medium.com article search and scraper",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("login", help="Authenticate via browser (run once)")

    def _listing_args(p):
        p.add_argument("-n", "--results", type=int, default=20, metavar="N")
        p.add_argument("--json", action="store_true")

    p_search = sub.add_parser("search", help="Search articles")
    p_search.add_argument("query", nargs="+")
    _listing_args(p_search)

    p_tag = sub.add_parser("tag", help="List articles by tag")
    p_tag.add_argument("tag")
    _listing_args(p_tag)

    p_author = sub.add_parser("author", help="List articles by author")
    p_author.add_argument("username", help="@username (with or without @)")
    _listing_args(p_author)

    p_pub = sub.add_parser("publication", help="List articles by publication")
    p_pub.add_argument("slug", help="Publication slug, e.g. towards-data-science")
    _listing_args(p_pub)

    p_read = sub.add_parser("read", help="Fetch full article text")
    p_read.add_argument("url")
    p_read.add_argument("--json", action="store_true")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "login":
        cmd_login()
        return

    listing_cmds = {
        "search":      lambda: cmd_search(" ".join(args.query), args.results),
        "tag":         lambda: cmd_tag(args.tag, args.results),
        "author":      lambda: cmd_author(args.username, args.results),
        "publication": lambda: cmd_publication(args.slug, args.results),
    }

    if args.command in listing_cmds:
        results = listing_cmds[args.command]()
        if args.json:
            print(json.dumps(results, ensure_ascii=False, indent=2))
        else:
            print_listing(results)
        return

    if args.command == "read":
        article = cmd_read(args.url)
        if args.json:
            print(json.dumps(article, ensure_ascii=False, indent=2))
        else:
            print_article(article)
        return


if __name__ == "__main__":
    main()
