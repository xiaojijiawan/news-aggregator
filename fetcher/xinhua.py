import httpx
from bs4 import BeautifulSoup
from .base import BaseFetcher, NewsItem, is_valid_news_title

XINHUA_URLS = [
    "http://www.news.cn/politics/xhjj.htm",
    "http://www.news.cn/",
]

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


class XinhuaFetcher(BaseFetcher):

    async def fetch(self) -> list[NewsItem]:
        items = []
        async with httpx.AsyncClient(timeout=15) as client:
            for url in XINHUA_URLS:
                try:
                    resp = await client.get(url, headers=HEADERS)
                    soup = BeautifulSoup(resp.text, "html.parser")
                    for link in soup.select("a[href]"):
                        title = link.get_text(strip=True)
                        href = link.get("href", "")
                        if not is_valid_news_title(title):
                            continue
                        if not href.startswith("http"):
                            if href.startswith("/"):
                                href = "http://www.news.cn" + href
                            else:
                                continue
                        # Try to get brief from nearby elements
                        brief = ""
                        parent = link.parent
                        if parent:
                            for tag in parent.select("p, span, .desc, .abstract, .summary"):
                                t = tag.get_text(strip=True)
                                if len(t) > 10 and t != title:
                                    brief = t
                                    break
                        items.append(NewsItem(
                            title=title, url=href, summary=brief, source="新华网",
                        ))
                except Exception:
                    pass

        seen = set()
        unique = []
        for item in items:
            if item.url not in seen:
                seen.add(item.url)
                unique.append(item)
        return unique

    async def fetch_content(self, item: NewsItem) -> str:
        if item.content:
            return item.content
        if item.summary and len(item.summary) > 30:
            return item.summary
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(item.url, headers=HEADERS)
                soup = BeautifulSoup(resp.text, "html.parser")
                # Meta description first
                meta = soup.select_one("meta[name=description]")
                if meta:
                    desc = meta.get("content", "")
                    if len(desc) > 20:
                        return desc[:2000]
                # Article body selectors
                for sel in [".article", "#detailContent", ".content", ".main-content",
                            "article", ".article-content", ".news-text"]:
                    body = soup.select_one(sel)
                    if body:
                        text = body.get_text(separator="\n", strip=True)
                        if len(text) > 100:
                            return text[:3000]
                paras = soup.select("p")
                text = "\n".join(p.get_text(strip=True) for p in paras if len(p.get_text(strip=True)) > 20)
                return text[:3000] if text else item.summary
        except Exception:
            return item.summary
