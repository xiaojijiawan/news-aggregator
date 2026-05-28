"""Generate static HTML dashboard — used by GitHub Actions CI."""
import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader

ROOT = Path(__file__).parent

# Ensure the project root is on sys.path so imports work
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fetcher.cctv import CctvFetcher
from fetcher.xinhua import XinhuaFetcher
from fetcher.bilibili import BilibiliFetcher
from fetcher.toutiao import ToutiaoFetcher
from classifier import classify_all
from summarizer import configure as configure_llm, generate_briefing, generate_overall

TEMPLATE_DIR = ROOT / "reporter" / "templates"
CATEGORY_PRIORITY = {"科技": 0, "电力能源": 1, "金属稀土": 2, "国际": 3, "政策": 4, "财经": 5, "民生": 6, "热点": 7}
CATEGORY_ORDER = ["科技", "电力能源", "金属稀土", "国际", "政策", "财经", "民生", "热点"]


def cap_news_items(items: list[dict], limit: int = 50) -> list[dict]:
    items.sort(key=lambda x: CATEGORY_PRIORITY.get(x.get("category", "热点"), 99))
    return items[:limit]


def build_page_data(today_items: list[dict], summaries: dict[str, str],
                    overall: str, generated_at: str) -> dict:
    groups: dict[str, list[dict]] = {}
    for i in today_items:
        cat = i.get("category", "热点")
        groups.setdefault(cat, []).append(i)

    sorted_groups = {k: groups[k] for k in CATEGORY_ORDER if k in groups}
    for k in groups:
        if k not in sorted_groups:
            sorted_groups[k] = groups[k]

    return {
        "groups": sorted_groups,
        "summaries": summaries or {},
        "overall": overall or "",
        "total": len(today_items),
        "generated_at": generated_at,
        "category_json": json.dumps(
            {k: len(v) for k, v in sorted_groups.items()}, ensure_ascii=False
        ),
    }


async def generate():
    config_path = ROOT / "config.yaml"
    if not config_path.exists():
        print("config.yaml not found — check CI secrets injection.")
        sys.exit(1)

    with open(config_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    # Init LLM
    configure_llm(config["deepseek"]["api_key"], config["deepseek"].get("model", "deepseek-chat"))

    # Fetch from all sources
    print("Fetching news...")
    fetchers = [CctvFetcher(), XinhuaFetcher(), BilibiliFetcher(), ToutiaoFetcher()]
    results = await asyncio.gather(*[f.fetch() for f in fetchers])

    all_items = []
    for items in results:
        all_items.extend(items)
    print(f"  Fetched {len(all_items)} raw items")

    # Dedup by URL (CI runs are fresh, no cross-session DB)
    seen_urls = set()
    unique = []
    for item in all_items:
        if item.url and item.url not in seen_urls:
            seen_urls.add(item.url)
            unique.append(item)
    print(f"  After dedup: {len(unique)}")

    # Classify
    classified = classify_all(unique)

    # Build display list (no DB — use classified items directly)
    today_items = [
        {"title": it.title, "url": it.url, "summary": it.summary,
         "content": it.content, "source": it.source, "category": it.category}
        for it in classified
    ]

    # Cap at 50
    today_items = cap_news_items(today_items)
    print(f"  After cap: {len(today_items)} items")

    # Group for summarization
    groups: dict[str, list[dict]] = {}
    for i in today_items:
        groups.setdefault(i.get("category", "热点"), []).append(i)

    # Generate LLM summaries
    print("Generating summaries (DeepSeek)...")
    summaries = await generate_briefing(groups)
    overall = await generate_overall(summaries)

    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    data = build_page_data(today_items, summaries, overall, generated_at)

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
