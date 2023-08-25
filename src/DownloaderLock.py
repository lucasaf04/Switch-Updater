import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import List

import toml

from Paths import DOWNLOADS_CACHE_PATH, DOWNLOADS_LOCK


@dataclass(frozen=True)
class DownloaderLock:
    repo: str
    tag_name: str
    asset_name: str
    asset_updated_at: str

    def __eq__(self, rhs: "DownloaderLock") -> bool:
        return (
            self.repo == rhs.repo
            and self.tag_name == rhs.tag_name
            and self.asset_name == rhs.asset_name
            and self.asset_updated_at == rhs.asset_updated_at
        )

    def cached_asset_path(self) -> Path:
        identifier_data = (
            f"{self.asset_updated_at} {Path(self.asset_name).name}".encode("utf-8")
        )
        identifier_hash = hashlib.sha256(identifier_data).hexdigest()
        return DOWNLOADS_CACHE_PATH / identifier_hash / self.asset_name


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
