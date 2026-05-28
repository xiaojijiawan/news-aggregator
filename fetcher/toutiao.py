"""今日头条热榜抓取器"""
import httpx
from .base import BaseFetcher, NewsItem, is_valid_news_title

TOUTIAO_API = "https://www.toutiao.com/hot-event/hot-board/?origin=toutiao_pc"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://www.toutiao.com/",
}


class ToutiaoFetcher(BaseFetcher):

    async def fetch(self) -> list[NewsItem]:
        items = []
        async with httpx.AsyncClient(timeout=15) as client:
            try:
                resp = await client.get(TOUTIAO_API, headers=HEADERS)
                data = resp.json()
                for entry in data.get("data", []):
                    title = entry.get("Title", "").strip()
                    if not title or len(title) < 4:
                        continue
                    url = entry.get("Url", entry.get("ArticleUrl", ""))
                    hot = entry.get("HotValue", 0)
                    items.append(NewsItem(
                        title=title,
                        url=url if url else f"https://so.toutiao.com/search?keyword={title}",
                        summary=f"头条热榜热度 {hot}",
                        source="今日头条",
                    ))
            except Exception:
                pass

        return items

    async def fetch_content(self, item: NewsItem) -> str:
        return item.summary
