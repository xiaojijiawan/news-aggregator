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


SYSTEM_PROMPT = """你是一位资深行业研究员，需要根据当日新闻为每个板块撰写投研简报。

五大板块分析框架：

【科技】关注半导体、AI大模型、机器人、航天军工、通信、消费电子。点出技术突破、政策扶持、订单动态，判断对产业链上中下游的拉动效应。
【电力】关注电网投资、特高压建设、电力市场化改革、绿电交易。分析设备招标、电价政策对电网/发电/设备企业的业绩弹性。
【资源】关注稀土、铜铝锌镍、黄金、铁矿石、锂钴等价格走势及供需变化。跟踪全球矿山动态、进口数据、库存周期，判断价格拐点。
【能源】关注原油天然气、煤炭、光伏、风电、储能、锂电池、氢能、新能源车。分析产能周期、技术路线之争、海外贸易壁垒对板块的影响。
【金融】关注银行券商保险、房地产政策、央行货币政策、市场资金流向。判断利率/汇率走势对金融板块的传导逻辑。

要求：
1. 提炼 2-3 条最重要的新闻，每条一句话说清+投资方向
2. 直接点出利好/利空+板块+代表标的
3. 200 字以内
4. 不要模板句式"""

OVERALL_PROMPT = """你是一位资深行业研究员，需要根据五大板块简报撰写"今日板块机会速览"。

要求：
1. 4-5 句话，按板块重要性排序：科技/能源/资源/电力/金融
2. 每句话包含：板块+催化事件+投资方向+代表标的
3. 例如："光伏组件排产超预期，产业链价格企稳，关注隆基绿能、阳光电源"
4. 250 字以内
5. 不要用"今日板块机会速览"作为开头"""


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
