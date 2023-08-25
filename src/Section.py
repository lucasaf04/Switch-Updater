from dataclasses import dataclass
from typing import List

from Downloader import Downloader
from SectionId import SectionId


@dataclass(frozen=True)
class SectionItem:
    downloader: Downloader
    to_remove: List[str]


@dataclass(frozen=True)
class Section:
    id: SectionId
    items: List[SectionItem]
