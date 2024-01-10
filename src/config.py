import logging
import re
from typing import Any, Dict, List, Optional

import toml

from downloader import DownloaderInitError, create_downloader
from paths import DOWNLOADS_TOML, GITHUB_TOKEN
from section import Section, SectionItem
from section_id import get_section_id


def parse_downloads_toml() -> List[Section]:
    with open(DOWNLOADS_TOML, "r", encoding="utf-8") as toml_file:
        toml_string = toml_file.read()

    toml_dict: Dict[str, List[Dict[str, Any]]] = toml.loads(toml_string)

    section_list: List[Section] = []
    for s_name, s_data in toml_dict.items():
        asset_list: List[SectionItem] = []
        for d_data in s_data:
            try:
                downloader = create_downloader(
                    d_data.get("repo"),
                    d_data.get("asset_name"),
                    d_data.get("asset_regex"),
                    d_data.get("file"),
                    d_data.get("url"),
                )
            except RuntimeError as err:
                raise DownloaderInitError(str(err), s_name) from None

            asset_list.append(
                SectionItem(
                    downloader,
                    d_data.get("remove", []),
                )
            )

        section_list.append(Section(get_section_id(s_name), asset_list))

    return section_list


def get_github_token() -> Optional[str]:
    with open(GITHUB_TOKEN, "r", encoding="utf-8") as token_file:
        token = token_file.read().strip()

    if re.match(r"^ghp_[a-zA-Z0-9]{36}$", token):
        return token

    logging.warning("Invalid GitHub token `%s`", token)
    return None
