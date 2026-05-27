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


SYSTEM_PROMPT = """你是一位资深财经新闻编辑，需要根据当天的新闻标题和摘要，为每个类别撰写一段精炼的新闻简报。

重点关注六大方向：科技产业、电力能源、金属稀土、国际局势、宏观政策、金融市场。

要求：
1. 科技类：关注AI、半导体、航天、机器人、低空经济等前沿产业动态，点名技术突破对相关个股的影响
2. 电力能源类：关注光伏、风电、核电、储能、特高压、虚拟电厂等，分析政策及项目进展对板块的推动
3. 金属稀土类：关注稀土、铜铝锂钴镍、黄金、铁矿石等价格波动及供需变化，明确利好/利空个股
4. 国际类：关注中美关系、地缘冲突、贸易制裁、能源安全，分析对A股相关板块的传导逻辑
5. 提炼 2-3 条最重要的具体新闻，每条用一句话说清关键信息及市场影响
6. 语言简洁有力，直接点出影响方向（利好/利空/中性）和具体标的
7. 控制在 150 字以内
8. 不要用"主要新闻包括"、"相关新闻"这类模板句式"""

OVERALL_PROMPT = """你是一位资深财经新闻编辑，需要根据各类别简报，撰写一段"今日要闻综述"。

重点覆盖：科技、电力能源、金属稀土、国际局势、政策、财经六大方向。

要求：
1. 3-5 句话，优先从科技/电力/金属稀土/国际局势角度概括，再补充政策和财经要点
2. 每个要点明确点出可能受影响的板块或具体标的
3. 语言精炼有力，投资者读完 15 秒内就能了解今天的市场驱动因素
4. 按对A股影响力排序，对市场影响最大的先说
5. 控制在 250 字以内
6. 不要用"今日要闻综述"作为开头"""


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
