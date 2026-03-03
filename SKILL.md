---
name: medium-scraper
description: Use when searching Medium.com articles, scraping article text, listing posts by tag/author/publication, or working with ~/medium.py CLI tool.
---

# Medium Scraper

CLI tool at `~/medium.py` to search and scrape Medium.com. Requires login once via Playwright.

## Setup (once)

```bash
pip install beautifulsoup4 curl_cffi playwright
playwright install chromium
python3 ~/medium.py login   # Opens browser → log in → press Enter
```

Cookies saved to `~/.medium/storage_state.json`.

## Quick Reference

| Command | What it does |
|---------|-------------|
| `login` | Open browser, save cookies |
| `search <query>` | Full-text search (Apollo State) |
| `tag <tag>` | Latest by tag (RSS, 10 items) |
| `author <@username>` | Latest by author (RSS, 10 items) |
| `publication <slug>` | Latest by publication (RSS, 10 items) |
| `read <url>` | Full article text + author |

**Flags (all listing commands):** `-n N` (count, default 20), `--json`

**Flag (read):** `--json`

## Examples

```bash
# Search
python3 ~/medium.py search "machine learning" -n 10
python3 ~/medium.py search "rust async" --json

# Tag
python3 ~/medium.py tag python -n 20
python3 ~/medium.py tag data-science -n 5

# Author (with or without @)
python3 ~/medium.py author @gvanrossum -n 10
python3 ~/medium.py author cassidoo

# Publication (medium.com slug)
python3 ~/medium.py publication better-programming -n 5
python3 ~/medium.py publication uxdesign -n 10

# Read full article
python3 ~/medium.py read "https://medium.com/better-programming/some-article-abc123"
python3 ~/medium.py read "https://medium.com/..." --json | jq '.text'
```

## Output Fields

```json
{
  "title": "Article Title",
  "url": "https://medium.com/...",
  "author": "Author Name",
  "username": "authorhandle",
  "date": "2026-03-01",
  "reading_time": 5,
  "claps": 142
}
```

`read` additionally returns `"text"` with full article body (headings prefixed `## `, code blocks fenced).

## Notes

- **Cloudflare bypass:** uses `curl_cffi` with `impersonate="chrome110"` — do not replace with `httpx`
- **Search** parses `window.__APOLLO_STATE__` from HTML (returns ~10 results)
- **Tag/author/publication** use RSS feeds → only 10 items max, no `claps`/`reading_time`
- **Publications with own domain** (e.g. `towardsdatascience.com`) don't work via `publication` — use `read <url>` directly
- Re-run `login` if requests start failing (cookies expire after ~30 days)
