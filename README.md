# medium-scraper

CLI tool to search and scrape Medium.com articles. Requires a Medium account.

## Setup

```bash
pip install -r requirements.txt
playwright install chromium

# Login once (opens browser)
python3 medium.py login
```

## Usage

```bash
# Search
python3 medium.py search "machine learning" -n 10
python3 medium.py search "rust programming" --json

# By tag
python3 medium.py tag python -n 20

# By author
python3 medium.py author @gvanrossum -n 10

# By publication
python3 medium.py publication better-programming -n 10

# Read full article text
python3 medium.py read "https://medium.com/..."
python3 medium.py read "https://medium.com/..." --json
```

## Options

| Flag | Description |
|------|-------------|
| `-n N` / `--results N` | Number of results (default: 20) |
| `--json` | Output as JSON |

## How it works

- **Login**: Playwright opens Chromium, you log in manually, cookies are saved to `~/.medium/storage_state.json`
- **Search**: Parses `window.__APOLLO_STATE__` from Medium's server-rendered HTML
- **Tag / Author / Publication**: Uses Medium's RSS feeds (`medium.com/feed/...`)
- **Article text**: Fetches HTML and parses with BeautifulSoup
- **Cloudflare bypass**: Uses `curl_cffi` to impersonate Chrome's TLS fingerprint
