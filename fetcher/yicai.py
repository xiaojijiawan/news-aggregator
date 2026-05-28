"""第一财经抓取器 — 权威财经新闻"""
import httpx
from .base import BaseFetcher, NewsItem

YICAI_API = "https://www.yicai.com/api/ajax/getlatest"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://www.yicai.com/",
}


class YicaiFetcher(BaseFetcher):

    async def fetch(self) -> list[NewsItem]:
        items = []
        async with httpx.AsyncClient(timeout=15) as client:
            try:
                resp = await client.get(
                    YICAI_API,
                    params={"page": 1, "pagesize": 50},
                    headers=HEADERS,
                )
                data = resp.json()
                for entry in data:
                    title = entry.get("NewsTitle", "").strip()
                    if not title or len(title) < 6:
                        continue
                    path = entry.get("url", "")
                    url = f"https://www.yicai.com{path}" if path else ""
                    summary = entry.get("NewsSummary", entry.get("NewsContent", "")).strip()
                    items.append(NewsItem(
                        title=title,
                        url=url,
                        summary=summary[:300],
                        source="第一财经",
                    ))
            except Exception:
                pass
        return items

    async def fetch_content(self, item: NewsItem) -> str:
        return item.summary
