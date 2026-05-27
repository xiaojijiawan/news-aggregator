"""News aggregator web server — keeps running, serves dashboard, refresh on demand."""
import asyncio
import json
import time
from datetime import datetime
from pathlib import Path

import yaml
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from jinja2 import Environment, FileSystemLoader

from db import init_db, insert_news, get_today_news, save_summaries, get_cached_summaries
from fetcher.cctv import CctvFetcher
from fetcher.xinhua import XinhuaFetcher
from fetcher.bilibili import BilibiliFetcher
from fetcher.base import NewsItem
from dedup import dedup
from classifier import classify_all
from summarizer import configure as configure_llm, generate_briefing, generate_overall

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    config = load_config()
    configure_llm(config["deepseek"]["api_key"], config["deepseek"].get("model", "deepseek-chat"))
    yield

app = FastAPI(lifespan=lifespan)
ROOT = Path(__file__).parent
TEMPLATE_DIR = ROOT / "reporter" / "templates"
CONFIG_PATH = ROOT / "config.yaml"

# Rate limit tracking
_last_refresh: float = 0
COOLDOWN = 3600  # 1 hour


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_template():
    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)))
    return env.get_template("live_dashboard.html")


CATEGORY_PRIORITY = {"科技": 0, "电力能源": 1, "金属稀土": 2, "国际": 3, "政策": 4, "财经": 5, "民生": 6, "热点": 7}

def cap_news_items(items: list[dict], limit: int = 50) -> list[dict]:
    """Keep top N items, prioritizing non-热点 categories."""
    if len(items) <= limit:
        return items
    items.sort(key=lambda x: CATEGORY_PRIORITY.get(x.get("category", "热点"), 99))
    return items[:limit]


def build_page_data(today_items: list[dict], summaries: dict[str, str],
                    overall: str, generated_at: str) -> dict:
    groups: dict[str, list[dict]] = {}
    for i in today_items:
        cat = i.get("category", "热点")
        groups.setdefault(cat, []).append(i)

    category_order = ["科技", "电力能源", "金属稀土", "国际", "政策", "财经", "民生", "热点"]
    sorted_groups = {k: groups[k] for k in category_order if k in groups}
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


async def run_news_pipeline() -> dict:
    """Run the full pipeline and return page data."""
    config = load_config()
    fetchers = [CctvFetcher(), XinhuaFetcher(), BilibiliFetcher()]
    tasks = [f.fetch() for f in fetchers]
    results = await asyncio.gather(*tasks)

    all_items = []
    for items in results:
        all_items.extend(items)

    unique = dedup(all_items)
    classified = classify_all(unique)

    for item in classified:
        insert_news(item.url, item.title, item.category, item.source, item.summary, item.content)

    today_items = get_today_news()
    today_urls = {i["url"] for i in today_items}
    for item in classified:
        if item.url not in today_urls:
            today_items.append({
                "title": item.title, "url": item.url,
                "summary": item.summary, "content": item.content,
                "source": item.source, "category": item.category,
            })

    today_items = cap_news_items(today_items)

    groups: dict[str, list[dict]] = {}
    for i in today_items:
        groups.setdefault(i.get("category", "热点"), []).append(i)

    summaries = await generate_briefing(groups)
    overall = await generate_overall(summaries)
    save_summaries(summaries, overall)
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    return build_page_data(today_items, summaries, overall, generated_at)


# --- Routes ---

@app.get("/", response_class=HTMLResponse)
async def index():
    """Serve the live dashboard page. Load existing data if available."""
    today_items = get_today_news()
    data = None
    if today_items:
        today_items = cap_news_items(today_items)
        cached = get_cached_summaries()
        summaries = {k: v for k, v in cached.items() if k != "__overall__"}
        overall = cached.get("__overall__", "")
        latest = max(i["fetched_at"] for i in today_items) if today_items else ""
        data = build_page_data(
            today_items, summaries, overall,
            latest or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )

    template = get_template()
    html = template.render(
        data=data,
        cooldown=COOLDOWN,
        last_refresh=int(_last_refresh * 1000),
        has_data=data is not None,
    )
    return html


@app.get("/api/status")
async def api_status():
    """Return current status: whether refresh is available."""
    now = time.time()
    elapsed = now - _last_refresh
    remaining = max(0, COOLDOWN - elapsed)
    return JSONResponse({
        "can_refresh": elapsed >= COOLDOWN or _last_refresh == 0,
        "remaining_seconds": int(remaining),
        "last_refresh": int(_last_refresh * 1000),
    })


@app.post("/api/refresh")
async def api_refresh():
    """Trigger a news fetch. Rate-limited. Returns lightweight status; page reloads to get data."""
    global _last_refresh
    now = time.time()
    elapsed = now - _last_refresh

    if _last_refresh > 0 and elapsed < COOLDOWN:
        remaining = int(COOLDOWN - elapsed)
        return JSONResponse({"ok": False, "error": "请等待后再刷新",
                              "remaining_seconds": remaining}, status_code=429)

    try:
        await run_news_pipeline()
        _last_refresh = now
        return JSONResponse({"ok": True, "message": "新闻已更新"})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


if __name__ == "__main__":
    import uvicorn
    init_db()
    print("\n新闻聚合服务器已启动: http://localhost:8888\n")
    uvicorn.run(app, host="0.0.0.0", port=8888, log_level="warning")
