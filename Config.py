import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import toml

from Downloader import Downloader, DownloaderInitError, DownloaderLock
from Section import Section, SectionId, SectionItem

BASE_PATH: Path = Path.cwd()
DOWNLOADS_TOML: Path = BASE_PATH / "downloads.toml"
DOWNLOADS_LOCK: Path = BASE_PATH / "downloads.lock"
GITHUB_TOKEN: Path = BASE_PATH / "github.token"
ROOT_SAVE_PATH: Path = BASE_PATH / "sd"
SAVE_PATHS: Dict[SectionId, Path] = {
    SectionId.BOOTLOADER: ROOT_SAVE_PATH,
    SectionId.FIRMWARE: ROOT_SAVE_PATH,
    SectionId.PAYLOADS: ROOT_SAVE_PATH / "bootloader/payloads",
    SectionId.NRO_APPS: ROOT_SAVE_PATH / "switch",
    SectionId.ATMOSPHERE_MODULES: ROOT_SAVE_PATH / "atmosphere/contents",
    SectionId.OVERLAYS: ROOT_SAVE_PATH / "switch/.overlays",
    SectionId.TEGRAEXPLORER_SCRIPTS: ROOT_SAVE_PATH / "tegraexplorer/scripts",
}


def parse_downloads_toml() -> List[Section]:
    with open(DOWNLOADS_TOML, "r", encoding="utf-8") as toml_file:
        toml_string = toml_file.read()

    toml_dict: Dict[str, Dict[str, Dict[str, Any]]] = toml.loads(toml_string)

    section_list: List[Section] = []
    for s_name, s_data in toml_dict.items():
        asset_list: List[SectionItem] = []
        for d_name, d_data in s_data.items():
            try:
                downloader = Downloader(
                    d_data.get("repo"),
                    d_data.get("asset_name"),
                    d_data.get("asset_regex"),
                    d_data.get("file"),
                    d_data.get("url"),
                )
            except RuntimeError as err:
                raise DownloaderInitError(str(err), d_name) from None

            asset_list.append(
                SectionItem(
                    downloader,
                    d_data.get("remove", []),
                )
            )

        section_list.append(Section(SectionId.parse(s_name), asset_list))

    return section_list


def parse_downloads_lock() -> List[DownloaderLock]:
    try:
        with open(DOWNLOADS_LOCK, "r", encoding="utf-8") as toml_file:
            toml_string = toml_file.read()

        toml_dict = toml.loads(toml_string)

        return [DownloaderLock(**lock) for lock in toml_dict.get("package", [])]
    except FileNotFoundError:
        return []


def save_downloads_lock(lock_list: List[DownloaderLock]) -> None:
    packages_list = [
        {
            "repo": lock.repo,
            "tag_name": lock.tag_name,
            "asset_name": lock.asset_name,
            "asset_updated_at": lock.asset_updated_at,
        }
        for lock in lock_list
    ]

    toml_dict = {"package": packages_list}
    toml_string = toml.dumps(toml_dict)

    with open(DOWNLOADS_LOCK, "w", encoding="utf-8") as toml_file:
        toml_file.write(toml_string)


def get_github_token() -> Optional[str]:
    with open(GITHUB_TOKEN, "r", encoding="utf-8") as token_file:
        token = token_file.read().strip()

    if re.match(r"^ghp_[a-zA-Z0-9]{36}$", token):
        return token

    logging.warning("Invalid GitHub token `%s`", token)
    return None
