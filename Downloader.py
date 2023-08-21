import logging
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from zipfile import ZipFile

import requests

from Config import ROOT_SAVE_PATH, SAVE_PATHS
from main import remove_from_root
from Section import Section

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

    @staticmethod
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

    @staticmethod
    def _get_latest_release(
        repo: str, token: Optional[str]
    ) -> Optional[Dict[str, Any]]:
        url = f"https://api.github.com/repos/{repo}/releases/latest"
        return Downloader._github_api_request(url, token)

    @staticmethod
    def _get_default_branch(repo: str, token: Optional[str]) -> Optional[str]:
        url = f"https://api.github.com/repos/{repo}"
        response = Downloader._github_api_request(url, token)

        return response.get("default_branch") if response is not None else None

    @staticmethod
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
            default_branch = Downloader._get_default_branch(self.repo, token)

            if default_branch is not None:
                url = f"https://raw.githubusercontent.com/{self.repo}/{default_branch}/{self.file}"
                message = f"\t{self.repo}: {Path(self.file).name}"
            else:
                print(f"Unable to get default branch for `{self.repo}`")
                return None
        elif self.repo is not None:
            latest_release = Downloader._get_latest_release(self.repo, token)

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
        downloaded_file_path = Downloader._download_file_to_temp_dir(url)

        if downloaded_file_path is None:
            return None

        print(message)
        logging.info("File downloaded to `%s`", downloaded_file_path)
        return downloaded_file_path


class DownloaderInitError(RuntimeError):
    def __init__(self, message, table_name):
        super().__init__(f"{message} in table `{table_name}`")


def _extract_zip(zip_file: ZipFile, target_path: Path):
    zip_file.extractall(target_path)
    logging.info("Zip file `%s` extracted to `%s`", zip_file.filename, target_path)


def _handle_zip(downloaded_file_path: Path, save_path: Path) -> None:
    try:
        with ZipFile(downloaded_file_path, "r") as zip_ref:
            zip_contents = zip_ref.namelist()
            is_single_file_zip = all("/" not in item for item in zip_contents)
            is_non_root_zip = any(
                keyword.lower() in zip_contents[0].lower()
                for keyword in ["sd/", "sdout/"]
            )

            if is_single_file_zip:
                _extract_zip(zip_ref, save_path)
            elif is_non_root_zip:
                _extract_zip(zip_ref, DOWNLOADS_TEMP_PATH)

                extracted_folder = DOWNLOADS_TEMP_PATH / zip_contents[0]
                shutil.copytree(extracted_folder, ROOT_SAVE_PATH, dirs_exist_ok=True)

                logging.info("`%s` moved to `%s`", extracted_folder, ROOT_SAVE_PATH)
                shutil.rmtree(extracted_folder)
            else:
                _extract_zip(zip_ref, ROOT_SAVE_PATH)
    except Exception as err:
        raise RuntimeError(f"Error while extracting the zip file: {err}") from err


def download_all(
    section_list: List[Section], lock_list: List[DownloaderLock], token: Optional[str]
) -> None:
    ROOT_SAVE_PATH.mkdir(exist_ok=True)

    for section in section_list:
        print(f"Downloading {section.id.name.lower()}:")

        for item in section.items:
            downloaded_file_path = item.downloader.download(lock_list, token)
            save_path = SAVE_PATHS[section.id]

            if downloaded_file_path is not None:
                if downloaded_file_path.suffix == ".zip":
                    _handle_zip(downloaded_file_path, save_path)
                else:
                    save_path.mkdir(parents=True, exist_ok=True)
                    downloaded_file_path.replace(save_path / downloaded_file_path.name)

                remove_from_root(item.to_remove)
