import re
from difflib import SequenceMatcher
from db import get_recent_titles, is_duplicate


def _clean(text: str) -> str:
    return re.sub(r"[^一-鿿\w]", "", text.strip())


def title_similar(title: str, existing_titles: list[str], threshold: float = 0.85) -> bool:
    if not existing_titles:
        return False
    clean_title = _clean(title)
    if not clean_title:
        return True
    for existing in existing_titles:
        clean_existing = _clean(existing)
        if not clean_existing:
            continue
        ratio = SequenceMatcher(None, clean_title, clean_existing).ratio()
        if ratio >= threshold:
            return True
    return False


def dedup(news_items: list, days: int = 7) -> list:
    existing_titles = get_recent_titles(days)
    unique = []
    for item in news_items:
        if not item.title or not item.url:
            continue
        if is_duplicate(item.url, item.title):
            continue
        if title_similar(item.title, existing_titles):
            continue
        existing_titles.append(item.title)
        unique.append(item)
    return unique
