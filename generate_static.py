"""Generate static HTML dashboard — used by GitHub Actions CI. No LLM needed."""
import asyncio
import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"

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
CATEGORY_ORDER = ["科技", "能源", "资源", "电力", "金融"]
DISPLAY_LIMIT = 100
HIGHLIGHT_COUNT = 5

# ── Market Impact Scoring ──────────────────────────────────────────

# High-impact: stocks, policy shifts, price moves
STOCK_NAMES = [
    "宁德时代", "比亚迪", "贵州茅台", "隆基绿能", "通威股份", "阳光电源",
    "北方稀土", "紫金矿业", "天齐锂业", "赣锋锂业", "华友钴业",
    "中信证券", "华泰证券", "招商银行", "中国平安", "东方财富",
    "长江电力", "中国核电", "中芯国际", "寒武纪", "海光信息",
    "万科", "保利发展", "中国神华", "陕西煤业", "中国石油",
    "中金公司", "国电南瑞", "特变电工", "金风科技", "明阳智能",
    "洛阳钼业", "江西铜业", "山东黄金", "工商银行", "建设银行",
    "立讯精密", "韦尔股份", "三一重工", "恒瑞医药", "药明康德",
    "美的集团", "格力电器", "伊利股份", "五粮液", "海天味业",
    "小米", "腾讯", "阿里巴巴", "百度", "京东", "拼多多", "美团",
]

PRICE_KEYWORDS = [
    "暴涨", "暴跌", "涨停", "跌停", "大涨", "大跌", "飙升", "重挫",
    "突破", "创新高", "创新低", "反弹", "回调", "熔断", "崩盘",
    "涨停板", "跌停板", "翻倍", "腰斩",
]

POLICY_KEYWORDS = [
    "降息", "加息", "降准", "利率决议", "新规", "出台", "国务院", "政治局",
    "制裁", "关税", "贸易战", "出口管制", "实体清单", "技术封锁",
    "货币政策", "财政刺激", "产业规划", "试点", "改革", "深改委",
    "证监会", "发改委", "工信部", "央行", "美联储", "OPEC",
]

SECTOR_KEYWORDS = [
    "板块", "利好", "利空", "赛道", "风口", "景气", "需求爆发",
    "供需失衡", "缺口", "涨价", "降价", "扩产", "停产", "限产",
]

AUTH_SOURCES = {"华尔街见闻", "第一财经", "新华网", "央视新闻"}

def market_impact_score(item: dict) -> int:
    """Score a news item by its likely market impact."""
    text = f"{item.get('title','')} {item.get('summary','')}"
    score = 0

    # Stock names
    for s in STOCK_NAMES:
        if s in text:
            score += 8

    # Price movements
    for kw in PRICE_KEYWORDS:
        if kw in text:
            score += 8
            break  # one price keyword is enough

    # Policy shifts
    for kw in POLICY_KEYWORDS:
        if kw in text:
            score += 8
            break

    # Sector impact
    for kw in SECTOR_KEYWORDS:
        if kw in text:
            score += 5
            break

    # Authoritative source
    if item.get("source", "") in AUTH_SOURCES:
        score += 5

    # Contains data (%, 亿, 万)
    if re.search(r'\d+%|\d+亿|\d+万', text):
        score += 3

    return score


# ── Data persistence ─────────────────────────────────────────────────

def save_daily_data(items: list[dict]):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    path = DATA_DIR / f"{today}.json"
    path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  Saved {len(items)} items to {path}")


def load_recent_data(days: int = 30) -> list[dict]:
    """Load news items from the last N days of data files."""
    all_items = []
    seen = set()
    cutoff = datetime.now() - timedelta(days=days)
    if not DATA_DIR.exists():
        return all_items
    for f in sorted(DATA_DIR.glob("*.json")):
        try:
            date_str = f.stem
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            if dt < cutoff:
                continue
            items = json.loads(f.read_text(encoding="utf-8"))
            for item in items:
                url = item.get("url", "")
                if url and url not in seen:
                    seen.add(url)
                    item["_date"] = date_str
                    all_items.append(item)
        except Exception:
            pass
    return all_items


def get_monthly_highlights() -> tuple[list[dict], list[dict]]:
    """Return (top 3 finance, top 2 industry) from last 30 days."""
    recent = load_recent_data(30)
    if not recent:
        return [], []

    finance = [item for item in recent if item.get("category") == "金融"]
    industry = [item for item in recent if item.get("category") != "金融"]

    fin_scored = [(market_impact_score(item), item) for item in finance]
    fin_scored.sort(key=lambda x: -x[0])
    top_finance = [item for _, item in fin_scored[:3]]

    ind_scored = [(market_impact_score(item), item) for item in industry]
    ind_scored.sort(key=lambda x: -x[0])
    top_industry = [item for _, item in ind_scored[:2]]

    return top_finance, top_industry


# ── Page building ────────────────────────────────────────────────────

def cap_news_items(items: list[dict]) -> list[dict]:
    if len(items) <= DISPLAY_LIMIT:
        return items
    priority = {"科技": 0, "能源": 1, "资源": 2, "电力": 3, "金融": 4}
    items.sort(key=lambda x: priority.get(x.get("category", "金融"), 99))
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

    # Save daily data for monthly highlights
    save_daily_data(today_items[:100])

    # Cap for display
    today_items = cap_news_items(today_items)
    print(f"  After cap: {len(today_items)} items")

    # Get monthly highlights: 3 finance + 2 industry
    fin_highlights, ind_highlights = get_monthly_highlights()
    print(f"  Monthly highlights: {len(fin_highlights)} finance + {len(ind_highlights)} industry")

    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    data = build_page_data(today_items, generated_at)

    # Render static page
    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)))
    template = env.get_template("static_dashboard.html")
    html = template.render(
        data=data,
        fin_highlights=fin_highlights,
        ind_highlights=ind_highlights,
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
