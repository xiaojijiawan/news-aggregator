from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import re

# Titles matching these patterns are navigation/boilerplate, not news
TITLE_BLOCKLIST = [
    re.compile(r"许可证$|许可证\s*\(|许可证京|许可证（京）"),
    re.compile(r"ICP[备证]|ICP备|ICP证"),
    re.compile(r"备案$|备案号|备案信息|备案（"),
    re.compile(r"信息网络传播视听节目"),
    re.compile(r"广播电视节目制作经营"),
    re.compile(r"网络文化经营许可"),
    re.compile(r"京公网安备"),
    re.compile(r"药品医疗器械网络信息服务"),
    re.compile(r"Copyright|©"),
    re.compile(r"^\s*$"),
]

def is_valid_news_title(title: str) -> bool:
    for pat in TITLE_BLOCKLIST:
        if pat.search(title):
            return False
    return len(title) >= 8


@dataclass
class NewsItem:
    title: str
    url: str
    summary: str = ""
    content: str = ""
    source: str = ""
    category: str = ""

class BaseFetcher(ABC):

    @abstractmethod
    async def fetch(self) -> list[NewsItem]:
        ...

    @abstractmethod
    async def fetch_content(self, item: NewsItem) -> str:
        ...
