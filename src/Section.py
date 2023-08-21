from dataclasses import dataclass
from enum import Enum, auto
from typing import List

from Downloader import Downloader


class SectionId(Enum):
    BOOTLOADER = auto()
    FIRMWARE = auto()
    PAYLOADS = auto()
    NRO_APPS = auto()
    ATMOSPHERE_MODULES = auto()
    OVERLAYS = auto()
    TEGRAEXPLORER_SCRIPTS = auto()


_nameToSectionId = {
    "bootloader": SectionId.BOOTLOADER,
    "firmware": SectionId.FIRMWARE,
    "payloads": SectionId.PAYLOADS,
    "nro_apps": SectionId.NRO_APPS,
    "atmosphere_modules": SectionId.ATMOSPHERE_MODULES,
    "overlays": SectionId.OVERLAYS,
    "tegraexplorer_scripts": SectionId.TEGRAEXPLORER_SCRIPTS,
}


def getSectionId(section_name: str):
    result = _nameToSectionId.get(section_name)
    if result is None:
        raise RuntimeError(f"Unsupported section name: `{section_name}`")
    return result


@dataclass
class SectionItem:
    downloader: Downloader
    to_remove: List[str]


@dataclass
class Section:
    id: SectionId
    items: List[SectionItem]