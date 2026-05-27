import json
from datetime import datetime
from pathlib import Path
from jinja2 import Environment, FileSystemLoader
from fetcher.base import NewsItem

TEMPLATE_DIR = Path(__file__).parent / "templates"
OUTPUT_DIR = Path(__file__).parent.parent / "output"


def generate_html(items: list[NewsItem], summaries: dict[str, str] = None,
                  overall: str = "", output_path: str = "") -> str:
    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)))
    template = env.get_template("dashboard.html")

    groups: dict[str, list[dict]] = {}
    for item in items:
        cat = item.category or "热点"
        groups.setdefault(cat, []).append({
            "title": item.title,
            "url": item.url,
            "summary": item.summary,
            "content": item.content,
            "source": item.source,
        })

    category_order = ["政策", "财经", "科技", "民生", "热点"]
    sorted_groups = {k: groups[k] for k in category_order if k in groups}
    for k, v in groups.items():
        if k not in sorted_groups:
            sorted_groups[k] = v

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    summaries = summaries or {}

    html = template.render(
        groups=sorted_groups,
        total=len(items),
        summaries=summaries,
        overall=overall,
        generated_at=now,
        category_json=json.dumps({k: len(v) for k, v in sorted_groups.items()}, ensure_ascii=False),
    )

    path = Path(output_path or str(OUTPUT_DIR / "news_dashboard.html")).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")
    return str(path)
