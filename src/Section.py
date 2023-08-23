from dataclasses import dataclass
from typing import List

from Downloader import Downloader
from SectionId import SectionId


@dataclass
class SectionItem:
    downloader: Downloader
    to_remove: List[str]


@dataclass
class Section:
    id: SectionId
    items: List[SectionItem]
