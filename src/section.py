from dataclasses import dataclass
from typing import List

from downloader import Downloader
from section_id import SectionId


@dataclass(frozen=True)
class SectionItem:
    downloader: Downloader
    to_remove: List[str]


@dataclass(frozen=True)
class Section:
    id: SectionId
    items: List[SectionItem]
