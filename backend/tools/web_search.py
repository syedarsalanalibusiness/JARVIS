from duckduckgo_search import DDGS


def search_web(query: str, max_results: int = 5) -> list[dict[str, str]]:
    """Search the public web and return a small citation-friendly result set."""
    try:
        raw = DDGS().text(query, max_results=max_results)
        return [
            {"title": item.get("title", "Untitled"), "url": item.get("href", ""), "snippet": item.get("body", "")}
            for item in raw if item.get("href")
        ]
    except Exception as exc:
        return [{"title": "Search unavailable", "url": "", "snippet": f"JARVIS could not search right now: {exc}"}]
