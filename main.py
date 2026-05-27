import asyncio
import argparse
import yaml
import webbrowser
from pathlib import Path
from db import init_db, insert_news, get_today_news
from fetcher.cctv import CctvFetcher
from fetcher.xinhua import XinhuaFetcher
from fetcher.bilibili import BilibiliFetcher
from dedup import dedup
from classifier import classify_all
from summarizer import configure as configure_llm, generate_briefing, generate_overall
from reporter.html_generator import generate_html
from scheduler import start_scheduler

CONFIG_PATH = Path(__file__).parent / "config.yaml"


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


async def run_once(config: dict):
    configure_llm(config["deepseek"]["api_key"], config["deepseek"].get("model", "deepseek-chat"))
    print("开始抓取新闻...")
    fetchers = [CctvFetcher(), XinhuaFetcher(), BilibiliFetcher()]
    tasks = [f.fetch() for f in fetchers]
    results = await asyncio.gather(*tasks)

    all_items = []
    for items in results:
        all_items.extend(items)

    print(f"抓取到 {len(all_items)} 条原始新闻")

    # Dedup
    unique = dedup(all_items)
    print(f"去重后剩余 {len(unique)} 条")

    # Classify
    classified = classify_all(unique)

    # Persist
    for item in classified:
        insert_news(item.url, item.title, item.category, item.source, item.summary, item.content)

    # Build display list from today's DB
    today_items = get_today_news()
    today_urls = {item["url"] for item in today_items}
    for item in classified:
        if item.url not in today_urls:
            today_items.append({
                "title": item.title, "url": item.url,
                "summary": item.summary, "content": item.content,
                "source": item.source, "category": item.category,
            })

    from fetcher.base import NewsItem
    display_items = [
        NewsItem(title=i["title"], url=i["url"],
                 summary=i.get("summary", ""), content=i.get("content", ""),
                 source=i["source"], category=i.get("category", "热点"))
        for i in today_items
    ]

    # Group for summarization
    groups: dict[str, list[dict]] = {}
    for i in today_items:
        cat = i.get("category", "热点")
        groups.setdefault(cat, []).append(i)

    # Generate summaries
    print("生成新闻摘要...")
    summaries = await generate_briefing(groups)
    overall = await generate_overall(summaries)

    # Generate HTML
    html_path = generate_html(display_items, summaries, overall,
                              config.get("output", {}).get("html_path", ""))
    print(f"HTML 简报已生成: {html_path} (今日共 {len(display_items)} 条)")

    # Open browser
    webbrowser.open(html_path)
    print("完成。")


def main():
    parser = argparse.ArgumentParser(description="新闻热点聚合系统")
    parser.add_argument("--once", action="store_true", help="手动运行一次")
    parser.add_argument("--serve", action="store_true", help="启动定时调度（每天 8:30）")
    args = parser.parse_args()

    init_db()
    config = load_config()

    if args.once:
        asyncio.run(run_once(config))
    elif args.serve:
        schedule_time = config.get("schedule", {}).get("time", "08:30")
        scheduler = start_scheduler(lambda: run_once(config), schedule_time)
        try:
            asyncio.get_event_loop().run_forever()
        except KeyboardInterrupt:
            print("调度器已停止")
    else:
        asyncio.run(run_once(config))


if __name__ == "__main__":
    main()
