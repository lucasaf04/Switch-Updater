import argparse
import re
import shutil
import tempfile
import zipfile
from dataclasses import dataclass, fields
from enum import Enum, auto
from pathlib import Path
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
    def _download_file_to_temp_dir(url: str) -> Optional[Path]:
        try:
            file_path = DOWNLOADS_TEMP_PATH / Path(url).name
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

    def download(self) -> Optional[Path]:
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
            asset_name = Path(asset_url).name
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


def download_all(section_list: List[Section]) -> None:
    ROOT_SAVE_PATH.mkdir(exist_ok=True)

    for section in section_list:
        print(f"Downloading {section.id.name.lower()}:")

        for downloader in section.downloader_list:
            downloaded_file_path = downloader.download()
            save_path = SAVE_PATHS[section.id]

            if downloaded_file_path is not None:
                debug(f"File downloaded to `{downloaded_file_path}`")

                if downloaded_file_path.suffix == ".zip":
                    _handle_zip(downloaded_file_path, save_path)
                else:
                    downloaded_file_path.replace(save_path / downloaded_file_path.name)


def _handle_zip(downloaded_file_path: Path, save_path: Path):
    try:
        with zipfile.ZipFile(downloaded_file_path, "r") as zip_ref:

            def _extract_zip(zip_file: ZipFile, target_path: Path):
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

                extracted_folder = DOWNLOADS_TEMP_PATH / zip_contents[0]
                shutil.copytree(extracted_folder, ROOT_SAVE_PATH, dirs_exist_ok=True)

                debug(f"`{extracted_folder}` moved to `{ROOT_SAVE_PATH}`")
                shutil.rmtree(extracted_folder)
            else:
                _extract_zip(zip_ref, ROOT_SAVE_PATH)
    except Exception as err:
        raise RuntimeError(f"Error while extracting the zip file: {err}") from err


def parse_downloads(file_path: Path) -> List[Section]:
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


def parse_downloads_lock(file_path: Path) -> List[DownloaderLock]:
    try:
        with open(file_path, "r", encoding="utf-8") as toml_file:
            toml_string = toml_file.read()

        toml_dict = toml.loads(toml_string)

        return [DownloaderLock(**lock) for lock in toml_dict.get("package", [])]
    except FileNotFoundError:
        return []


def save_downloads_lock(file_path: Path) -> None:
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


def create_payload():
    for file in ROOT_SAVE_PATH.iterdir():
        if re.search(r"hekate_ctcaer_(?:\d+\.\d+\.\d+)\.bin", file.name) is not None:
            new_path = file.with_name("payload.bin")
            file.rename(new_path)
            debug(f"Renamed `{file}` to `{new_path}`")
            break


if __name__ == "__main__":
    # todo: add GitHub token to remove the 40 requests per hour restriction

    DOWNLOADS_TOML: Path = Path.cwd() / "downloads.toml"
    DOWNLOADS_LOCK: Path = Path.cwd() / "downloads.lock"
    DOWNLOADS_TEMP_PATH: Path = Path(tempfile.mkdtemp())
    ROOT_SAVE_PATH: Path = Path.cwd() / "sd"
    SAVE_PATHS: Dict[SectionId, Path] = {
        SectionId.BOOTLOADER: ROOT_SAVE_PATH,
        SectionId.FIRMWARE: ROOT_SAVE_PATH,
        SectionId.PAYLOADS: ROOT_SAVE_PATH / "bootloader/payloads",
        SectionId.NRO_APPS: ROOT_SAVE_PATH / "switch",
        SectionId.ATMOSPHERE_MODULES: ROOT_SAVE_PATH / "atmosphere/contents",
        SectionId.OVERLAYS: ROOT_SAVE_PATH / "switch/.overlays",
    }
    CONFIG_FILES_PATH: Path = Path.cwd() / "config_files"

    cli_parser = argparse.ArgumentParser()
    cli_parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    cli_parser.add_argument("--mariko", action="store_true", help="Enable mariko mode")
    cli_parser.add_argument(
        "--rebuild", action="store_true", help="Delete previously downloaded files"
    )
    cli_parser.add_argument("--pack", help="Name of the zip file to create")
    cli_args = cli_parser.parse_args()

    DEBUG_ENABLED: bool = cli_args.debug

    if cli_args.rebuild:
        if ROOT_SAVE_PATH.exists():
            shutil.rmtree(ROOT_SAVE_PATH)
            debug(f"Removed `{ROOT_SAVE_PATH}`")

        if DOWNLOADS_LOCK.exists():
            DOWNLOADS_LOCK.unlink()
            debug(f"Removed `{DOWNLOADS_LOCK}`")

    downloads_section_list = parse_downloads(DOWNLOADS_TOML)
    DOWNLOADS_LOCK_LIST = parse_downloads_lock(DOWNLOADS_LOCK)
    download_all(downloads_section_list)
    save_downloads_lock(DOWNLOADS_LOCK)

    if cli_args.mariko:
        create_payload()
        # todo: remove reboot_to_payload.nro
        
    # todo: move .nro apps into folders

    if CONFIG_FILES_PATH.exists():
        shutil.copytree(CONFIG_FILES_PATH, ROOT_SAVE_PATH, dirs_exist_ok=True)
        print("Copied config files")

    if cli_args.pack is not None:
        shutil.make_archive(cli_args.pack, "zip", ROOT_SAVE_PATH)
        print(
            f"The directory '{ROOT_SAVE_PATH}' has been packed into '{cli_args.pack}.zip'"
        )
