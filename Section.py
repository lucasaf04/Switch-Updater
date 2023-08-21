from dataclasses import dataclass
from enum import Enum, auto
from typing import List

from Downloader import Downloader


@dataclass
class SectionItem:
    downloader: Downloader
    to_remove: List[str]


class SectionId(Enum):
    BOOTLOADER = auto()
    FIRMWARE = auto()
    PAYLOADS = auto()
    NRO_APPS = auto()
    ATMOSPHERE_MODULES = auto()
    OVERLAYS = auto()
    TEGRAEXPLORER_SCRIPTS = auto()

    @staticmethod
    def parse(section_name: str):
        if section_name == "bootloader":
            return SectionId.BOOTLOADER
        if section_name == "firmware":
            return SectionId.FIRMWARE
        if section_name == "payloads":
            return SectionId.PAYLOADS
        if section_name == "nro_apps":
            return SectionId.NRO_APPS
        if section_name == "atmosphere_modules":
            return SectionId.ATMOSPHERE_MODULES
        if section_name == "overlays":
            return SectionId.OVERLAYS
        if section_name == "tegraexplorer_scripts":
            return SectionId.TEGRAEXPLORER_SCRIPTS

        raise RuntimeError(f"Unsupported section name: `{section_name}`")


@dataclass
class Section:
    id: SectionId
    items: List[SectionItem]
