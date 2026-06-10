"""Generate static HTML dashboard — used by GitHub Actions CI. No LLM needed."""
import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

ROOT = Path(__file__).parent

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fetcher.cctv import CctvFetcher
from fetcher.xinhua import XinhuaFetcher
from fetcher.bilibili import BilibiliFetcher
from fetcher.toutiao import ToutiaoFetcher
from fetcher.wallstreetcn import WallstreetcnFetcher
from fetcher.yicai import YicaiFetcher
from fetcher.baidu import BaiduFetcher
from classifier import classify_all

TEMPLATE_DIR = ROOT / "reporter" / "templates"

CATEGORY_PRIORITY = {"科技": 0, "能源": 1, "资源": 2, "电力": 3, "金融": 4}
CATEGORY_ORDER = ["科技", "能源", "资源", "电力", "金融"]

DISPLAY_LIMIT = 100  # show up to 100 items, no LLM bottleneck


def cap_news_items(items: list[dict]) -> list[dict]:
    if len(items) <= DISPLAY_LIMIT:
        return items
    items.sort(key=lambda x: CATEGORY_PRIORITY.get(x.get("category", "金融"), 99))
    return items[:DISPLAY_LIMIT]


def build_page_data(items: list[dict], generated_at: str) -> dict:
    groups: dict[str, list[dict]] = {}
    for i in items:
        cat = i.get("category", "金融")
        groups.setdefault(cat, []).append(i)

    sorted_groups = {k: groups[k] for k in CATEGORY_ORDER if k in groups}
    for k in groups:
        if k not in sorted_groups:
            sorted_groups[k] = groups[k]

    return {
        "groups": sorted_groups,
        "total": len(items),
        "generated_at": generated_at,
        "category_json": json.dumps(
            {k: len(v) for k, v in sorted_groups.items()}, ensure_ascii=False
        ),
    }


async def generate():
    print("Fetching news...")
    fetchers = [
        CctvFetcher(), XinhuaFetcher(),
        WallstreetcnFetcher(), YicaiFetcher(),
        ToutiaoFetcher(), BaiduFetcher(), BilibiliFetcher(),
    ]
    results = await asyncio.gather(*[f.fetch() for f in fetchers])

    all_items = []
    for items in results:
        all_items.extend(items)
    print(f"  Fetched {len(all_items)} raw items")

    # Dedup by URL
    seen_urls = set()
    unique = []
    for item in all_items:
        if item.url and item.url not in seen_urls:
            seen_urls.add(item.url)
            unique.append(item)
    print(f"  After dedup: {len(unique)}")

    # Classify
    classified = classify_all(unique)

    # Build display list
    today_items = [
        {"title": it.title, "url": it.url, "summary": it.summary,
         "source": it.source, "category": it.category}
        for it in classified
    ]

    # Cap
    today_items = cap_news_items(today_items)
    print(f"  After cap: {len(today_items)} items")

    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    data = build_page_data(today_items, generated_at)

    # Render static page
    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)))
    template = env.get_template("static_dashboard.html")
    html = template.render(
        data=data,
        generated_at=generated_at,
        repo_url=os.environ.get("REPO_URL", "#"),
        github_actions_url=os.environ.get("ACTIONS_URL", "#"),
    )

    output_path = ROOT / "output" / "index.html"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    print(f"HTML written to {output_path}")
    print("Done.")


if __name__ == "__main__":
    asyncio.run(generate())
