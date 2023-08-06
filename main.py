import argparse
import os
import re
import shutil
import tempfile
import zipfile
from dataclasses import dataclass, fields
from enum import Enum, auto
from typing import Any, Dict, List, Optional
from zipfile import ZipFile

import requests
import toml


def debug(*args, **kwargs) -> None:
    if DEBUG_ENABLED:
        print(*args, **kwargs)


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
    file: Optional[str]
    regex: Optional[str]
    url: Optional[str]

    def __init__(self, **kwargs: Optional[str]):
        for field in fields(self):
            setattr(self, field.name, kwargs.get(field.name, None))

    @staticmethod
    def _get_latest_release(repo: str) -> Optional[Any]:
        url = f"https://api.github.com/repos/{repo}/releases/latest"
        response = requests.get(url, timeout=5)

        if response.status_code == 200:
            return response.json()

        print(f"Request failed with status code: {response.status_code}")
        return None

    @staticmethod
    def _download_file_to_temp_dir(url: str) -> Optional[str]:
        try:
            file_path = os.path.join(DOWNLOADS_TEMP_PATH, os.path.basename(url))
            response = requests.get(url, timeout=5)

            if response.status_code == 200:
                with open(file_path, "wb") as file:
                    file.write(response.content)
                return file_path

            print(f"Failed to download the file. Status code: {response.status_code}")
            return None
        except Exception as err:
            raise RuntimeError(f"Error while downloading the file: {err}") from err

    def _get_asset(self, assets: Any) -> Optional[Any]:
        for asset in assets:
            name: str = asset["name"]

            if self.file is not None:
                if name.find(self.file) != -1:
                    return asset
            elif self.regex is not None:
                if re.search(self.regex, name) is not None:
                    return asset

        return None

    def _get_cached_lock(self) -> Optional[DownloaderLock]:
        for lock in DOWNLOADS_LOCK_LIST:
            if lock.repo == self.repo:
                if self.file is not None:
                    if lock.asset_name == self.file:
                        return lock
                elif self.regex is not None:
                    if re.search(self.regex, lock.asset_name) is not None:
                        return lock
        return None

    def download(self) -> Optional[str]:
        if self.repo is not None:
            latest_release = self._get_latest_release(self.repo)

            if latest_release is not None:
                asset = self._get_asset(latest_release["assets"])

                if asset is not None:
                    asset_name = asset["name"]
                    asset_url = asset["browser_download_url"]
                    message = f"\t{self.repo}: {asset_name}"

                    cached_lock = self._get_cached_lock()
                    current_lock = DownloaderLock(
                        repo=self.repo,
                        tag_name=latest_release["tag_name"],
                        asset_name=asset_name,
                        asset_updated_at=asset["updated_at"],
                    )

                    if cached_lock is not None:
                        if cached_lock == current_lock:
                            print(f"\t{self.repo}: Already up to date")
                            return None
                        DOWNLOADS_LOCK_LIST.remove(cached_lock)

                    DOWNLOADS_LOCK_LIST.append(current_lock)
                else:
                    print(f"Unable to get matching asset for `{self.repo}`")
                    return None
            else:
                print(f"Unable to get latest release for `{self.repo}`")
                return None
        elif self.url is not None:
            asset_url = self.url
            asset_name = os.path.basename(asset_url)
            message = f"\t{asset_name}"
        else:
            print("unreachable")
            return None

        downloaded_file_path = self._download_file_to_temp_dir(asset_url)

        if downloaded_file_path:
            print(message)
            return downloaded_file_path

        print(f"Failed to download `{asset_name}` from `{asset_url}`")
        return None


class SectionId(Enum):
    BOOTLOADER = auto()
    FIRMWARE = auto()
    PAYLOADS = auto()
    NRO_APPS = auto()
    ATMOSPHERE_MODULES = auto()
    OVERLAYS = auto()

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

        raise RuntimeError(f"Unsupported section name: `{section_name}`")


@dataclass
class Section:
    id: SectionId
    downloader_list: List[Downloader]


def _get_file_extension(file_path: str) -> str:
    _, extension = os.path.splitext(file_path)
    return extension


def _create_empty_folder(directory_path: str) -> None:
    try:
        os.makedirs(directory_path, exist_ok=True)
        debug(f"Directory `{directory_path}` created or already exists")
    except Exception as err:
        raise RuntimeError(f"Error while creating directory: {err}") from err


def _move_to_folder(source_path: str, target_path: str) -> None:
    try:
        target_path = os.path.join(target_path, os.path.basename(source_path))

        # replace the file if it already exists
        if os.path.exists(target_path):
            os.remove(target_path)

        shutil.move(source_path, target_path)
        debug(f"File moved to `{target_path}`")
    except Exception as err:
        raise RuntimeError(f"Error while saving the file: {err}") from err


def _move_folder_contents(source_folder: str, destination_folder: str):
    for item in os.listdir(source_folder):
        source_item = os.path.join(source_folder, item)
        destination_item = os.path.join(destination_folder, item)
        shutil.move(source_item, destination_item)


def download_all(section_list: List[Section]) -> None:
    _create_empty_folder(ROOT_SAVE_PATH)

    for section in section_list:
        print(f"Downloading {section.id.name.lower()}:")

        for downloader in section.downloader_list:
            downloaded_file_path = downloader.download()
            save_path = ROOT_SAVE_PATH + SAVE_PATHS[section.id]

            if downloaded_file_path is not None:
                debug(f"File downloaded to `{downloaded_file_path}`")

                if _get_file_extension(downloaded_file_path) == ".zip":
                    _handle_zip(downloaded_file_path, save_path)
                else:
                    _move_to_folder(downloaded_file_path, save_path)


def _handle_zip(downloaded_file_path: str, save_path: str):
    try:
        with zipfile.ZipFile(downloaded_file_path, "r") as zip_ref:

            def _extract_zip(zip_file: ZipFile, target_path: str):
                zip_file.extractall(target_path)
                debug(f"Zip file `{zip_file.filename}` extracted to `{target_path}`")

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

                extracted_folder = os.path.join(DOWNLOADS_TEMP_PATH, zip_contents[0])

                _move_folder_contents(extracted_folder, ROOT_SAVE_PATH)
                debug(f"`{extracted_folder}` moved to `{ROOT_SAVE_PATH}`")
                shutil.rmtree(extracted_folder)
            else:
                _extract_zip(zip_ref, ROOT_SAVE_PATH)
    except Exception as err:
        raise RuntimeError(f"Error while extracting the zip file: {err}") from err


def parse_downloads(file_path: str) -> List[Section]:
    with open(file_path, "r", encoding="utf-8") as toml_file:
        toml_string = toml_file.read()

    toml_dict: Dict[str, Dict[str, Dict[str, str]]] = toml.loads(toml_string)

    section_list: List[Section] = []
    for s_name, s_data in toml_dict.items():
        downloader_list: List[Downloader] = []
        for d_name, d_data in s_data.items():
            dwl = Downloader(**d_data)

            if (dwl.repo is None) == (dwl.url is None):
                raise RuntimeError(
                    f"Either `repo` or `url` must be provided in table `{d_name}`"
                )

            if (dwl.repo is not None) and ((dwl.file is None) == (dwl.regex is None)):
                raise RuntimeError(
                    f"Either `file` or `regex` must be provided in table `{d_name}`"
                )

            if (dwl.url is not None) and (
                dwl.file is not None or dwl.regex is not None
            ):
                raise RuntimeError(f"`url` must be provided alone in table `{d_name}`")

            downloader_list.append(dwl)

        section_list.append(
            Section(id=SectionId.parse(s_name), downloader_list=downloader_list)
        )

    return section_list


def parse_downloads_lock(file_path: str) -> List[DownloaderLock]:
    try:
        with open(file_path, "r", encoding="utf-8") as toml_file:
            toml_string = toml_file.read()

        toml_dict = toml.loads(toml_string)

        return [DownloaderLock(**lock) for lock in toml_dict.get("package", [])]
    except FileNotFoundError:
        return []


def save_downloads_lock(file_path: str) -> None:
    packages_list = [
        {
            "repo": lock.repo,
            "tag_name": lock.tag_name,
            "asset_name": lock.asset_name,
            "asset_updated_at": lock.asset_updated_at,
        }
        for lock in DOWNLOADS_LOCK_LIST
    ]

    toml_dict = {"package": packages_list}
    toml_string = toml.dumps(toml_dict)

    with open(file_path, "w", encoding="utf-8") as toml_file:
        toml_file.write(toml_string)


if __name__ == "__main__":
    DOWNLOADS_TOML: str = "downloads.toml"
    DOWNLOADS_LOCK: str = "downloads.lock"
    DOWNLOADS_TEMP_PATH: str = tempfile.mkdtemp()
    ROOT_SAVE_PATH: str = os.getcwd() + "/sd"
    SAVE_PATHS: Dict[SectionId, str] = {
        SectionId.BOOTLOADER: "/",
        SectionId.FIRMWARE: "/",
        SectionId.PAYLOADS: "/bootloader/payloads",
        SectionId.NRO_APPS: "/switch",
        SectionId.ATMOSPHERE_MODULES: "/atmosphere/contents",
        SectionId.OVERLAYS: "/switch/.overlays",
    }
    CONFIG_FILES_PATH: str = os.getcwd() + "/config_files"

    cli_parser = argparse.ArgumentParser()
    cli_parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    cli_parser.add_argument(
        "--rebuild", action="store_true", help="Delete previously downloaded files"
    )
    cli_parser.add_argument("--pack", help="Name of the zip file to create")
    cli_args = cli_parser.parse_args()

    DEBUG_ENABLED: bool = cli_args.debug

    if cli_args.rebuild:
        if os.path.exists(ROOT_SAVE_PATH):
            shutil.rmtree(ROOT_SAVE_PATH)
            debug(f"Removed `{ROOT_SAVE_PATH}`")

        if os.path.exists(DOWNLOADS_LOCK):
            os.remove(DOWNLOADS_LOCK)
            debug(f"Removed `{DOWNLOADS_LOCK}`")

    # todo: don't use a global DOWNLOADS_LOCK_SET ??
    downloads_section_list = parse_downloads(DOWNLOADS_TOML)
    DOWNLOADS_LOCK_LIST = parse_downloads_lock(DOWNLOADS_LOCK)
    download_all(downloads_section_list)
    save_downloads_lock(DOWNLOADS_LOCK)

    for filename in os.listdir(ROOT_SAVE_PATH):
        if re.search(r"hekate_ctcaer_(?:\d+\.\d+\.\d+)\.bin", filename) is not None:
            old_name = f"{ROOT_SAVE_PATH}/{filename}"
            new_name = f"{ROOT_SAVE_PATH}/payload.bin"
            os.rename(old_name, new_name)
            debug(f"Renamed `{old_name}` to `{new_name}`")
            break

    if os.path.exists(CONFIG_FILES_PATH):
        shutil.copytree(CONFIG_FILES_PATH, ROOT_SAVE_PATH, dirs_exist_ok=True)
        print("Copied config files")

    if cli_args.pack is not None:
        shutil.make_archive(cli_args.pack, "zip", ROOT_SAVE_PATH)
        print(
            f"The directory '{ROOT_SAVE_PATH}' has been packed into '{cli_args.pack}.zip'"
        )
