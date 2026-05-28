"""Generate news digests using DeepSeek LLM."""
import json
import re
import httpx

DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"

_api_key: str = ""
_model: str = "deepseek-chat"


def configure(api_key: str, model: str = "deepseek-chat"):
    global _api_key, _model
    _api_key = api_key
    _model = model


SYSTEM_PROMPT = """你是一位资深投研分析师，需要根据当日新闻撰写一份精炼的投资晨报。每个类别按以下框架分析：

【宏观政策】聚焦货币/财政政策、经济数据、产业规划。点明政策方向（宽松/收紧/中性），判断对大盘流动性及风险偏好的影响，标注利好的板块（如降准→券商、地产）。
【行业动态】聚焦产业政策、技术突破、供需变化、竞争格局。判断行业景气度方向（上行/下行/震荡），点出直接受益/受损的细分赛道和龙头个股。
【公司基本面】聚焦财报、重大合同、并购重组、高管变动、增减持。用一句话说清事件本质及对估值的影响，标注潜在的交易机会或风险。
【市场情绪】聚焦资金流向、成交量、两融数据、热点题材发酵。判断市场风险偏好（贪婪/恐惧/中性），辅助把握买卖时机。
【国际局势】聚焦地缘政治、国际贸易、大宗商品、美联储动态。分析对A股的传导路径及影响板块（如原油涨→利好油气开采、利空航空）。

要求：
1. 提炼 2-3 条最重要的新闻，每条一句话说清关键信息+市场影响方向
2. 直接点出利好/利空和具体标的（个股、板块、ETF）
3. 控制在 200 字以内
4. 不要用"主要新闻包括"、"相关新闻"等模板句式"""

OVERALL_PROMPT = """你是一位资深投研分析师，需要根据各类别简报，撰写一段"今日投资要点"。

按对A股影响力排序，优先覆盖宏观政策拐点、重大行业催化、国际事件传导。

要求：
1. 4-5 句话，直接回答：今天投资者最需要关注的是什么？
2. 每个要点明确投资含义（利好/利空+板块/个股+逻辑）
3. 例如："央行意外降准50bp，短期利好券商、地产板块，关注中信证券、万科A"
4. 控制在 250 字以内
5. 不要用"今日投资要点"作为开头"""


def _noise_score(title: str) -> int:
    """Score how likely a title is noise."""
    patterns = ["许可证", "ICP", "备案", "Copyright", "©", "京公网安备",
                "广播电视", "信息网络", "视听节目", "网络文化"]
    return sum(1 for p in patterns if p in title)


async def _call_llm(system: str, user: str) -> str:
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(DEEPSEEK_URL, headers={
            "Authorization": f"Bearer {_api_key}",
            "Content-Type": "application/json",
        }, json={
            "model": _model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.3,
            "max_tokens": 500,
        })
        data = resp.json()
        if resp.status_code != 200:
            raise RuntimeError(f"DeepSeek API error: {data}")
        return data["choices"][0]["message"]["content"].strip()


async def summarize_category(articles: list[dict]) -> str:
    if not articles:
        return "暂无相关新闻。"

    # Filter noise, keep top articles
    clean = [(a, _noise_score(a.get("title", ""))) for a in articles]
    clean.sort(key=lambda x: x[1])
    top = [a for a, s in clean if s == 0][:20]
    if not top:
        top = [a for a, s in clean][:10]

    # Build input: titles + briefs
    lines = []
    for a in top:
        brief = a.get("summary", "").strip()
        if brief and len(brief) > 5:
            lines.append(f"《{a['title']}》——{brief}")
        else:
            lines.append(f"《{a['title']}》")

    if not lines:
        return "暂无重要新闻。"

    user_input = f"以下是今日新闻列表，请撰写简报：\n\n" + "\n".join(lines)

    try:
        result = await _call_llm(SYSTEM_PROMPT, user_input)
        return result
    except Exception as e:
        return f"[摘要生成失败: {e}]"


async def generate_briefing(groups: dict[str, list[dict]]) -> dict[str, str]:
    summaries = {}
    for cat, articles in groups.items():
        summaries[cat] = await summarize_category(articles)
    return summaries


async def generate_overall(summaries: dict[str, str]) -> str:
    parts = []
    for cat, text in summaries.items():
        if text and "暂无" not in text:
            parts.append(f"【{cat}】{text}")

    if not parts:
        return "今日暂无重要新闻。"

    user_input = "以下是各类别简报，请撰写今日综述：\n\n" + "\n\n".join(parts)

    try:
        return await _call_llm(OVERALL_PROMPT, user_input)
    except Exception as e:
        return f"[综述生成失败: {e}]"
