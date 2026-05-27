import httpx
from bs4 import BeautifulSoup
from .base import BaseFetcher, NewsItem, is_valid_news_title

CCTV_API = "https://news.cctv.com/2019/07/gaiban/cmsdatainterface/page/news_1.jsonp"

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


class CctvFetcher(BaseFetcher):

    async def fetch(self) -> list[NewsItem]:
        items = []
        async with httpx.AsyncClient(timeout=15) as client:
            try:
                resp = await client.get(CCTV_API, headers={"Referer": "https://news.cctv.com/"})
                text = resp.text
                if text.startswith("callback("):
                    import json
                    json_str = text[9:-1]
                    data = json.loads(json_str)
                    for entry in data.get("data", {}).get("list", []):
                        title = entry.get("title", "").strip()
                        if not is_valid_news_title(title):
                            continue
                        items.append(NewsItem(
                            url=entry.get("url", ""),
                            summary=entry.get("brief", "").strip(),
                            source="央视新闻",
                        ))
            except Exception:
                pass

            if not items:
                try:
                    resp = await client.get("https://news.cctv.com/", headers=HEADERS)
                    soup = BeautifulSoup(resp.text, "html.parser")
                    for link in soup.select("a[href]"):
                        title = link.get_text(strip=True)
                        href = link["href"]
                        if len(title) >= 8 and "news.cctv.com" in href:
                            items.append(NewsItem(title=title, url=href, source="央视新闻"))
                except Exception:
                    pass

        return items

    async def fetch_content(self, item: NewsItem) -> str:
        if item.content:
            return item.content
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(item.url, headers=HEADERS)
                soup = BeautifulSoup(resp.text, "html.parser")
                # Try common article body selectors
                for sel in [".content_area", ".article-content", "#content_area",
                            "article", ".text", ".cnt_bd", ".info_text"]:
                    body = soup.select_one(sel)
                    if body:
                        text = body.get_text(separator="\n", strip=True)
                        if len(text) > 100:
                            return text[:3000]
                # Fallback: grab all paragraphs
                paras = soup.select("p")
                text = "\n".join(p.get_text(strip=True) for p in paras if len(p.get_text(strip=True)) > 20)
                return text[:3000] if text else item.summary
        except Exception:
            return item.summary
