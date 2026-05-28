"""华尔街见闻快讯抓取器 — 权威财经实时信息"""
import httpx
from .base import BaseFetcher, NewsItem

WALLST_API = "https://api-one.wallstcn.com/apiv1/content/lives"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://wallstreetcn.com/",
}


class WallstreetcnFetcher(BaseFetcher):

    async def fetch(self) -> list[NewsItem]:
        items = []
        async with httpx.AsyncClient(timeout=15) as client:
            try:
                resp = await client.get(
                    WALLST_API,
                    params={"channel": "global-channel", "limit": 50},
                    headers=HEADERS,
                )
                data = resp.json()
                for entry in data.get("data", {}).get("items", []):
                    title = entry.get("title", "").strip()
                    content = entry.get("content_text", "").strip()
                    if not content and not title:
                        continue
                    # Flash news often has empty title, use content_text as title
                    if not title and content:
                        title = content[:60] + ("..." if len(content) > 60 else "")
                    elif not title:
                        continue
                    uri = entry.get("uri", "")
                    items.append(NewsItem(
                        title=title,
                        url=uri if uri else f"https://wallstreetcn.com/livenews/{entry.get('id', '')}",
                        summary=content[:300] if content else "",
                        source="华尔街见闻",
                    ))
            except Exception:
                pass
        return items

    async def fetch_content(self, item: NewsItem) -> str:
        return item.summary
