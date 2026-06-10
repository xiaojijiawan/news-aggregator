"""百度热搜抓取器"""
import httpx
import re
from urllib.parse import quote
from .base import BaseFetcher, NewsItem

BAIDU_API = "https://top.baidu.com/board?tab=realtime"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://www.baidu.com/",
}


class BaiduFetcher(BaseFetcher):

    async def fetch(self) -> list[NewsItem]:
        items = []
        async with httpx.AsyncClient(timeout=15) as client:
            try:
                resp = await client.get(BAIDU_API, headers=HEADERS)
                text = resp.text
                # Extract word, desc, hotScore from embedded JSON
                words = re.findall(r'"word":"([^"]+)"', text)
                descs = re.findall(r'"desc":"([^"]*)"', text)
                scores = re.findall(r'"hotScore":"([^"]*)"', text)
                for i, word in enumerate(words[:50]):
                    if len(word) < 2:
                        continue
                    desc = descs[i] if i < len(descs) else ""
                    items.append(NewsItem(
                        title=word,
                        url=f"https://www.baidu.com/s?wd={quote(word)}",
                        summary=desc,
                        source="百度热搜",
                    ))
            except Exception:
                pass
        return items

    async def fetch_content(self, item: NewsItem) -> str:
        return item.summary
