import logging
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from urllib.parse import unquote, urlparse, urlunparse

import requests

from downloader_lock import DownloaderLock
from paths import DOWNLOADS_TEMP_PATH


class DownloadError(RuntimeError):
    def __init__(self, filename: str, orig_error: requests.exceptions.RequestException):
        super().__init__(f"Error while downloading `{filename}`: {orig_error}")


class DownloaderInitError(RuntimeError):
    def __init__(self, message: str, table_name: str):
        super().__init__(f"{message} in table array `{table_name}`")


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


def _download_file_to(target_path: Path, url: str) -> Optional[Path]:
    filename = _get_file_name_from_url(url)

    try:
        response = requests.get(url, timeout=10, headers={"cache-control": "no-cache"})
    except requests.exceptions.RequestException as err:
        raise DownloadError(filename, err) from None

    if response.status_code != 200:
        print(f"Failed to download `{filename}`. Status code: {response.status_code}")
        return None

    target_path.mkdir(parents=True, exist_ok=True)

    file_path = target_path / filename
    with open(file_path, "wb") as file:
        file.write(response.content)
        return file_path


def _get_file_name_from_url(url: str) -> str:
    parsed_url = urlparse(unquote(url))
    path_url = urlunparse(
        (
            parsed_url.scheme,
            parsed_url.netloc,
            parsed_url.path,
            "",
            "",
            "",
        )
    )
    return Path(path_url).name


@dataclass(frozen=True)
class GithubFile:
    _repo: str
    _file: str

    def download(
        self,
        token: Optional[str],
    ) -> Optional[Path]:
        print(f"\t{self._repo}: {Path(self._file).name}")

        default_branch = _get_default_branch(self._repo, token)

        if default_branch is None:
            print(f"Unable to get default branch for `{self._repo}`")
            return None

        url = f"https://raw.githubusercontent.com/{self._repo}/{default_branch}/{self._file}"
        downloaded_file_path = _download_file_to(DOWNLOADS_TEMP_PATH, url)

        if downloaded_file_path is not None:
            logging.info("File downloaded to `%s`", downloaded_file_path)

        return downloaded_file_path


@dataclass(frozen=True)
class GithubAsset:
    _repo: str
    _asset_name: Optional[str]
    _asset_regex: Optional[str]

    def _get_asset(self, assets: Any) -> Optional[Any]:
        for asset in assets:
            asset_name: str = asset["name"]

            if self._asset_name is not None:
                if asset_name == self._asset_name:
                    return asset
            elif self._asset_regex is not None:
                if re.search(self._asset_regex, asset_name) is not None:
                    return asset

        return None

    def _get_cached_lock(
        self, lock_list: List[DownloaderLock]
    ) -> Optional[DownloaderLock]:
        for lock in lock_list:
            if lock.repo == self._repo:
                if self._asset_name is not None:
                    if lock.asset_name == self._asset_name:
                        return lock
                elif self._asset_regex is not None:
                    if re.search(self._asset_regex, lock.asset_name) is not None:
                        return lock
        return None

    def download(
        self,
        lock_list: List[DownloaderLock],
        token: Optional[str],
    ) -> Optional[Path]:
        latest_release = _get_latest_release(self._repo, token)

        if latest_release is None:
            print(f"Unable to get latest release for `{self._repo}`")
            return None

        asset = self._get_asset(latest_release["assets"])

        if asset is None:
            print(f"Unable to get matching asset for `{self._repo}`")
            return None

        asset_name = asset["name"]
        current_lock = DownloaderLock(
            self._repo,
            latest_release["tag_name"],
            asset_name,
            asset["updated_at"],
        )
        cached_lock = self._get_cached_lock(lock_list)

        if cached_lock is not None:
            cached_asset_path = cached_lock.cached_asset_path()

            if cached_lock == current_lock:
                print(f"\t{self._repo}: Already up to date")
                return cached_asset_path

            shutil.rmtree(cached_asset_path.parent)
            logging.info("Removed `%s`", cached_asset_path.parent)

            lock_list.remove(cached_lock)

        print(f"\t{self._repo}: {asset_name}")

        url = asset["browser_download_url"]

        downloaded_file_path = _download_file_to(
            current_lock.cached_asset_path().parent, url
        )

        if downloaded_file_path is not None:
            logging.info("File downloaded to `%s`", downloaded_file_path)
            lock_list.append(current_lock)

        return downloaded_file_path


@dataclass(frozen=True)
class RawUrl:
    _url: str

    def download(
        self,
    ) -> Optional[Path]:
        print(f"\t{_get_file_name_from_url(self._url)}")

        downloaded_file_path = _download_file_to(DOWNLOADS_TEMP_PATH, self._url)

        if downloaded_file_path is not None:
            logging.info("File downloaded to `%s`", downloaded_file_path)

        return downloaded_file_path


@dataclass(frozen=True)
class Downloader:
    _downloader_type: Union[GithubFile, GithubAsset, RawUrl]

    def download(
        self,
        lock_list: List[DownloaderLock],
        token: Optional[str],
    ) -> Optional[Path]:
        if isinstance(self._downloader_type, GithubAsset):
            downloaded_file_path = self._downloader_type.download(lock_list, token)
        elif isinstance(self._downloader_type, GithubFile):
            downloaded_file_path = self._downloader_type.download(token)
        elif isinstance(self._downloader_type, RawUrl):
            downloaded_file_path = self._downloader_type.download()
        else:
            raise AssertionError("This branch should be unreachable.")

        return downloaded_file_path


def create_downloader(
    repo: Optional[str],
    asset_name: Optional[str],
    asset_regex: Optional[str],
    file: Optional[str],
    url: Optional[str],
) -> Downloader:
    if (repo is None) == (url is None):
        raise RuntimeError("Either `repo` or `url` must be provided")

    if (repo is not None) and (
        (asset_name is None) == (asset_regex is None) == (file is None)
    ):
        raise RuntimeError(
            "Either `asset_name`, `asset_regex` or `file` must be provided"
        )

    if (url is not None) and (
        asset_name is not None or asset_regex is not None or file is not None
    ):
        raise RuntimeError("`url` must be provided alone")

    if repo and (asset_name or asset_regex):
        return Downloader(GithubAsset(repo, asset_name, asset_regex))

    if repo and file:
        return Downloader(GithubFile(repo, file))

    if url:
        return Downloader(RawUrl(url))

    raise AssertionError("This branch should be unreachable.")
