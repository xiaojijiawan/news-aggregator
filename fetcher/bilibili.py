import httpx
from urllib.parse import quote
from .base import BaseFetcher, NewsItem, is_valid_news_title

BILIBILI_API = "https://api.bilibili.com/x/web-interface/search/square?limit=50"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://www.bilibili.com/",
}


class BilibiliFetcher(BaseFetcher):

    async def fetch(self) -> list[NewsItem]:
        items = []
        async with httpx.AsyncClient(timeout=15) as client:
            try:
                resp = await client.get(BILIBILI_API, headers=HEADERS)
                data = resp.json()
                trending = data.get("data", {}).get("trending", {})
                for entry in trending.get("list", []):
                    keyword = entry.get("keyword", "").strip()
                    if not keyword or len(keyword) < 2:
                        continue
                    heat = entry.get("heat_score", 0)
                    items.append(NewsItem(
                        title=keyword,
                        url=f"https://search.bilibili.com/all?keyword={quote(keyword)}",
                        summary=f"热搜热度 {heat}",
                        source="哔哩哔哩热搜",
                    ))
            except Exception:
                pass

        return items

    async def fetch_content(self, item: NewsItem) -> str:
        return item.summary
