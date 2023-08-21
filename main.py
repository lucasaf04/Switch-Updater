import logging
import re
import shutil
import tempfile
from argparse import ArgumentParser, ArgumentTypeError
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from zipfile import ZipFile

import requests
import toml


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
    def _github_api_request(url: str, token: Optional[str]) -> Optional[Any]:
        if token is not None:
            headers = {
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "X-GitHub-Api-Version": "2022-11-28",
            }
        else:
            headers = None

        response = requests.get(url=url, headers=headers, timeout=5)

        if response.status_code == 200:
            return response.json()

        print(f"GitHub API Request failed. Status code: {response.status_code}")
        return None

    @staticmethod
    def _get_latest_release(repo: str, token: Optional[str]) -> Optional[Any]:
        url = f"https://api.github.com/repos/{repo}/releases/latest"
        return Downloader._github_api_request(url, token)

    @staticmethod
    def _get_default_branch(repo: str, token: Optional[str]) -> Optional[str]:
        url = f"https://api.github.com/repos/{repo}"
        response = Downloader._github_api_request(url, token)

        if response is None:
            return None

        return response.get("default_branch")

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
    ) -> Optional[Tuple[str, str, str]]:
        if self.repo is not None and self.file is not None:
            default_branch = Downloader._get_default_branch(self.repo, token)

            if default_branch is not None:
                url = f"https://raw.githubusercontent.com/{self.repo}/{default_branch}/{self.file}"
                filename = Path(self.file).name
                message = f"\t{self.repo}: {filename}"
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
            filename = Path(url).name
            message = f"\t{filename}"
        else:
            raise AssertionError("This branch should be unreachable.")

        return (url, filename, message)

    def download(
        self,
        lock_list: List[DownloaderLock],
        token: Optional[str],
    ) -> Optional[Path]:
        preparation = self._prepare_download(lock_list, token)
        if preparation is None:
            return None

        url, filename, message = preparation
        downloaded_file_path = Downloader._download_file_to_temp_dir(url)

        if downloaded_file_path is not None:
            print(message)
            logging.info("File downloaded to `%s`", downloaded_file_path)
            return downloaded_file_path

        print(f"Failed to download `{filename}` from `{url}`")
        return None


class DownloaderInitError(RuntimeError):
    def __init__(self, message, table_name):
        super().__init__(f"{message} in table `{table_name}`")


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


def _handle_zip(downloaded_file_path: Path, save_path: Path):
    try:
        with ZipFile(downloaded_file_path, "r") as zip_ref:

            def _extract_zip(zip_file: ZipFile, target_path: Path):
                zip_file.extractall(target_path)
                logging.info(
                    "Zip file `%s` extracted to `%s`", zip_file.filename, target_path
                )

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


def create_payload():
    for file in ROOT_SAVE_PATH.iterdir():
        if re.search(r"hekate_ctcaer_(?:\d+\.\d+\.\d+)\.bin", file.name) is not None:
            new_path = file.with_name("payload.bin")
            file.rename(new_path)
            logging.info("Renamed `%s` to `%s`", file, new_path)
            break


def remove_from_root(to_remove: List[str]):
    for item in to_remove:
        item = ROOT_SAVE_PATH / item
        if item.exists():
            if item.is_dir():
                shutil.rmtree(item)
            elif item.is_file():
                item.unlink()
            logging.info("Removed `%s`", item)


def move_nro_apps_into_folders() -> None:
    for item in SAVE_PATHS[SectionId.NRO_APPS].iterdir():
        if item.is_file() and item.suffix == ".nro":
            folder = item.parent / item.stem
            folder.mkdir(exist_ok=True)
            item.rename(folder / item.name)


def get_github_token() -> Optional[str]:
    with open(BASE_PATH / "github.token", "r", encoding="utf-8") as token_file:
        token = token_file.read().strip()

    if re.match(r"^ghp_[a-zA-Z0-9]{36}$", token):
        return token

    logging.info("Invalid GitHub token `%s`", token)
    return None


def valid_log_level(level: str):
    numeric_level = getattr(logging, level.upper(), None)
    if not isinstance(numeric_level, int):
        raise ArgumentTypeError(f"Invalid log level: `{level}`")
    return level


def main() -> None:
    cli_parser = ArgumentParser()
    cli_parser.add_argument(
        "--log",
        type=valid_log_level,
        default="ERROR",
        help=f"Set the log level: {', '.join(logging.getLevelNamesMapping().keys())} (default ERROR)",
    )
    cli_parser.add_argument("--mariko", action="store_true", help="Enable mariko mode")
    cli_parser.add_argument(
        "--no-config", action="store_true", help="Disable copying config files"
    )
    cli_parser.add_argument(
        "--rebuild", action="store_true", help="Delete previously downloaded files"
    )
    cli_parser.add_argument("--pack", help="Name of the zip file to create")
    cli_args = cli_parser.parse_args()

    logging.basicConfig(
        level=cli_args.log,
        format="[%(asctime)s %(levelname)s %(name)s] %(message)s",
    )

    if cli_args.rebuild:
        if ROOT_SAVE_PATH.exists():
            shutil.rmtree(ROOT_SAVE_PATH)
            logging.info("Removed `%s`", ROOT_SAVE_PATH)

        if DOWNLOADS_LOCK.exists():
            DOWNLOADS_LOCK.unlink()
            logging.info("Removed `%s`", DOWNLOADS_LOCK)

    downloads_section_list = parse_downloads_toml()
    downloads_lock_list = parse_downloads_lock()
    github_token = get_github_token()
    download_all(downloads_section_list, downloads_lock_list, github_token)
    save_downloads_lock(downloads_lock_list)

    if cli_args.mariko:
        create_payload()
        remove_from_root(["switch/reboot_to_payload.nro"])
    else:
        # todo
        print("Erista specific functionality not implemented")

    move_nro_apps_into_folders()

    if not cli_args.no_config:
        if CONFIG_FILES_PATH.exists():
            shutil.copytree(CONFIG_FILES_PATH, ROOT_SAVE_PATH, dirs_exist_ok=True)
            logging.info("Copied `%s` to `%s`", CONFIG_FILES_PATH, ROOT_SAVE_PATH)

    if cli_args.pack is not None:
        shutil.make_archive(cli_args.pack, "zip", ROOT_SAVE_PATH)
        logging.info(
            "The directory `%s` has been packed into `%s.zip`",
            ROOT_SAVE_PATH,
            cli_args.pack,
        )


if __name__ == "__main__":
    BASE_PATH: Path = Path.cwd()
    DOWNLOADS_TOML: Path = BASE_PATH / "downloads.toml"
    DOWNLOADS_LOCK: Path = BASE_PATH / "downloads.lock"
    DOWNLOADS_TEMP_PATH: Path = Path(tempfile.mkdtemp())
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
    CONFIG_FILES_PATH: Path = BASE_PATH / "config_files"

    main()
