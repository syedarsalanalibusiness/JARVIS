import html
import re
from urllib.parse import urlencode
from xml.etree import ElementTree

import httpx


def search_web(query: str, max_results: int = 5) -> list[dict[str, str]]:
    """Fetch current news from Google's public RSS search feed (no API key required)."""
    lower = query.lower()
    if re.search(r"[\u0600-\u06ff]", query):
        language, country, edition = "ur-PK", "PK", "PK:ur"
    elif re.search(r"[\u0900-\u097f]", query):
        language, country, edition = "hi-IN", "IN", "IN:hi"
    else:
        language, country, edition = "en-US", "US", "US:en"
    params = {"q": query, "hl": language, "gl": country, "ceid": edition}
    url = "https://news.google.com/rss/search?" + urlencode(params)
    try:
        response = httpx.get(
            url,
            headers={"User-Agent": "JARVIS school project/1.0"},
            timeout=10.0,
            follow_redirects=True,
        )
        response.raise_for_status()
        root = ElementTree.fromstring(response.content)
        results: list[dict[str, str]] = []
        for item in root.findall("./channel/item")[:max_results]:
            title = html.unescape(item.findtext("title", default="")).strip()
            link = item.findtext("link", default="").strip()
            description = html.unescape(item.findtext("description", default=""))
            snippet = re.sub(r"<[^>]+>", " ", description)
            snippet = re.sub(r"\s+", " ", snippet).strip()
            published = item.findtext("pubDate", default="").strip()
            if published:
                snippet = f"{published}. {snippet}".strip()
            if title and link:
                results.append({"title": title, "url": link, "snippet": snippet})
        return results
    except Exception as exc:
        return [{
            "title": "Current search unavailable",
            "url": "",
            "snippet": f"JARVIS could not fetch current results right now: {exc}",
        }]
