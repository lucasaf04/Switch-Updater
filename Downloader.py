import logging
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

DOWNLOADS_TEMP_PATH: Path = Path(tempfile.mkdtemp())


@dataclass
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


def _github_api_request(url: str, token: Optional[str]) -> Optional[Dict[str, Any]]:
    if token is not None:
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        }
    else:
        headers = None

    response = requests.get(url=url, headers=headers, timeout=5)

    if response.status_code != 200:
        print(f"GitHub API Request failed. Status code: {response.status_code}")
        return None

    return response.json()


def _get_latest_release(repo: str, token: Optional[str]) -> Optional[Dict[str, Any]]:
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    return _github_api_request(url, token)


def _get_default_branch(repo: str, token: Optional[str]) -> Optional[str]:
    url = f"https://api.github.com/repos/{repo}"
    response = _github_api_request(url, token)
    return response.get("default_branch") if response is not None else None


def _download_file_to_temp_dir(url: str) -> Optional[Path]:
    filename = Path(url).name
    try:
        file_path = DOWNLOADS_TEMP_PATH / filename
        response = requests.get(url, timeout=5)

        if response.status_code != 200:
            print(
                f"Failed to download `{filename}`. Status code: {response.status_code}"
            )
            return None

        with open(file_path, "wb") as file:
            file.write(response.content)
            return file_path

    except Exception as err:
        raise RuntimeError(f"Error while downloading `{filename}`: {err}") from err


@dataclass
class Downloader:
    repo: Optional[str]
    asset_name: Optional[str]
    asset_regex: Optional[str]
    file: Optional[str]
    url: Optional[str]

    def __post_init__(self):
        if (self.repo is None) == (self.url is None):
            raise RuntimeError("Either `repo` or `url` must be provided")

        if (self.repo is not None) and (
            (self.asset_name is None)
            == (self.asset_regex is None)
            == (self.file is None)
        ):
            raise RuntimeError(
                "Either `asset_name`, `asset_regex` or `file` must be provided"
            )

        if (self.url is not None) and (
            self.asset_name is not None
            or self.asset_regex is not None
            or self.file is not None
        ):
            raise RuntimeError("`url` must be provided alone")

    def _get_asset(self, assets: Any) -> Optional[Any]:
        for asset in assets:
            asset_name: str = asset["name"]

            if self.asset_name is not None:
                if asset_name == self.asset_name:
                    return asset
            elif self.asset_regex is not None:
                if re.search(self.asset_regex, asset_name) is not None:
                    return asset

        return None

    def _get_cached_lock(
        self, lock_list: List[DownloaderLock]
    ) -> Optional[DownloaderLock]:
        for lock in lock_list:
            if lock.repo == self.repo:
                if self.asset_name is not None:
                    if lock.asset_name == self.asset_name:
                        return lock
                elif self.asset_regex is not None:
                    if re.search(self.asset_regex, lock.asset_name) is not None:
                        return lock
        return None

    def _prepare_download(
        self,
        lock_list: List[DownloaderLock],
        token: Optional[str],
    ) -> Optional[Tuple[str, str]]:
        if self.repo is not None and self.file is not None:
            default_branch = _get_default_branch(self.repo, token)

            if default_branch is not None:
                url = f"https://raw.githubusercontent.com/{self.repo}/{default_branch}/{self.file}"
                message = f"\t{self.repo}: {Path(self.file).name}"
            else:
                print(f"Unable to get default branch for `{self.repo}`")
                return None
        elif self.repo is not None:
            latest_release = _get_latest_release(self.repo, token)

            if latest_release is not None:
                asset = self._get_asset(latest_release["assets"])

                if asset is not None:
                    filename = asset["name"]
                    url = asset["browser_download_url"]
                    message = f"\t{self.repo}: {filename}"

                    cached_lock = self._get_cached_lock(lock_list)
                    current_lock = DownloaderLock(
                        repo=self.repo,
                        tag_name=latest_release["tag_name"],
                        asset_name=filename,
                        asset_updated_at=asset["updated_at"],
                    )

                    if cached_lock is not None:
                        if cached_lock == current_lock:
                            print(f"\t{self.repo}: Already up to date")
                            return None
                        lock_list.remove(cached_lock)

                    lock_list.append(current_lock)
                else:
                    print(f"Unable to get matching asset for `{self.repo}`")
                    return None
            else:
                print(f"Unable to get latest release for `{self.repo}`")
                return None
        elif self.url is not None:
            url = self.url
            message = f"\t{Path(url).name}"
        else:
            raise AssertionError("This branch should be unreachable.")

        return (url, message)

    def download(
        self,
        lock_list: List[DownloaderLock],
        token: Optional[str],
    ) -> Optional[Path]:
        preparation = self._prepare_download(lock_list, token)

        if preparation is None:
            return None

        url, message = preparation
        downloaded_file_path = _download_file_to_temp_dir(url)

        if downloaded_file_path is None:
            return None

        print(message)
        logging.info("File downloaded to `%s`", downloaded_file_path)
        return downloaded_file_path


class DownloaderInitError(RuntimeError):
    def __init__(self, message, table_name):
        super().__init__(f"{message} in table `{table_name}`")
