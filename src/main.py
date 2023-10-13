import logging
import re
import shutil
from argparse import ArgumentParser, ArgumentTypeError
from pathlib import Path
from typing import List, Optional, Union
from zipfile import ZipFile

from Config import get_github_token, parse_downloads_toml
from Downloader import DownloadError
from DownloaderLock import DownloaderLock, parse_downloads_lock, save_downloads_lock
from Paths import (
    BASE_PATH,
    DOWNLOADS_CACHE_PATH,
    DOWNLOADS_LOCK,
    DOWNLOADS_TEMP_PATH,
    PC_SAVE_PATH,
    ROOT_SAVE_PATH,
    SAVE_PATHS,
)
from Section import Section
from SectionId import SectionId


def _extract_zip(zip_file: ZipFile, members: Optional[List[str]], target_path: Path):
    zip_file.extractall(target_path, members)
    logging.info("Zip file `%s` extracted to `%s`", zip_file.filename, target_path)


def _handle_zip(
    downloaded_file_path: Path, save_path: Path, to_remove: List[str]
) -> None:
    try:
        with ZipFile(downloaded_file_path, "r") as zip_ref:
            zip_contents = zip_ref.namelist()
            is_single_file_zip = all("/" not in item for item in zip_contents)
            is_non_root_zip = any(
                keyword.lower() in zip_contents[0].lower()
                for keyword in ["sd/", "sdout/"]
            )
            filtered_zip_contents = None

            if len(to_remove) > 0:
                filtered_zip_contents = [
                    filename
                    for filename in zip_contents
                    if not any(filename.startswith(prefix) for prefix in to_remove)
                ]

            if is_single_file_zip:
                _extract_zip(zip_ref, filtered_zip_contents, save_path)
            elif is_non_root_zip:
                _extract_zip(zip_ref, filtered_zip_contents, DOWNLOADS_TEMP_PATH)

                extracted_folder = DOWNLOADS_TEMP_PATH / zip_contents[0]
                shutil.copytree(extracted_folder, ROOT_SAVE_PATH, dirs_exist_ok=True)

                logging.info("`%s` moved to `%s`", extracted_folder, ROOT_SAVE_PATH)
                shutil.rmtree(extracted_folder)
            else:
                _extract_zip(zip_ref, filtered_zip_contents, ROOT_SAVE_PATH)
    except Exception as err:
        raise RuntimeError(f"Error while extracting the zip file: {err}") from err


def download_all(
    section_list: List[Section], lock_list: List[DownloaderLock], token: Optional[str]
) -> None:
    for section in section_list:
        print(f"Downloading {section.id.name.lower()}:")

        for item in section.items:
            try:
                downloaded_file_path = item.downloader.download(lock_list, token)
            except DownloadError as err:
                save_downloads_lock(lock_list)
                raise err

            save_path = SAVE_PATHS[section.id]

            if downloaded_file_path is not None:
                if downloaded_file_path.suffix == ".zip":
                    _handle_zip(downloaded_file_path, save_path, item.to_remove)
                else:
                    save_path.mkdir(parents=True, exist_ok=True)
                    target_file_path = save_path / downloaded_file_path.name
                    shutil.copyfile(downloaded_file_path, target_file_path)
                    logging.info(
                        "Copied`%s` to `%s`", downloaded_file_path, target_file_path
                    )


def move_file(
    source_path: Path,
    source_pattern: Union[str, re.Pattern[str]],
    target_path: Path,
    target_name: Optional[str] = None,
) -> None:
    for file in source_path.iterdir():
        if re.search(source_pattern, file.name) is not None:
            new_path = target_path / (
                target_name if target_name is not None else file.name
            )
            file.rename(new_path)
            logging.info("Renamed `%s` to `%s`", file, new_path)
            break


def remove_from_root(to_remove: List[str]) -> None:
    for item in to_remove:
        item = ROOT_SAVE_PATH / item
        if item.exists():
            if item.is_dir():
                shutil.rmtree(item)
            elif item.is_file():
                item.unlink()
            logging.info("Removed `%s`", item)


def move_nro_apps_into_folders() -> None:
    nro_apps_path = SAVE_PATHS[SectionId.NRO_APP]
    if nro_apps_path is None:
        return None

    for item in nro_apps_path.iterdir():
        if item.is_file() and item.suffix == ".nro":
            folder = item.parent / item.stem
            folder.mkdir(exist_ok=True)
            item.rename(folder / item.name)


def create_cli_parser() -> ArgumentParser:
    def valid_log_level(level: str) -> str:
        numeric_level = getattr(logging, level.upper(), None)
        if not isinstance(numeric_level, int):
            raise ArgumentTypeError(f"Invalid log level: `{level}`")
        return level

    valid_log_levels = ", ".join(logging.getLevelNamesMapping().keys())

    cli_parser = ArgumentParser()
    cli_parser.add_argument(
        "--log",
        type=valid_log_level,
        default="ERROR",
        help=f"Set the log level: {valid_log_levels} (default ERROR)",
    )
    cli_parser.add_argument("--mariko", action="store_true", help="Enable mariko mode")
    cli_parser.add_argument(
        "--no-config", action="store_true", help="Disable copying config files"
    )
    cli_parser.add_argument(
        "--remove-cache", action="store_true", help="Delete previously downloaded files"
    )
    cli_parser.add_argument("--pack", help="Name of the zip file to create")
    return cli_parser


def main() -> None:
    cli_parser = create_cli_parser()
    cli_args = cli_parser.parse_args()

    logging.basicConfig(
        level=cli_args.log,
        format="[%(asctime)s %(levelname)s %(name)s] %(message)s",
    )

    if ROOT_SAVE_PATH.exists():
        shutil.rmtree(ROOT_SAVE_PATH)
        logging.info("Removed `%s`", ROOT_SAVE_PATH)

    ROOT_SAVE_PATH.mkdir()
    logging.info("Created `%s`", ROOT_SAVE_PATH)

    if cli_args.remove_cache:
        if DOWNLOADS_LOCK.exists():
            DOWNLOADS_LOCK.unlink()
            logging.info("Removed `%s`", DOWNLOADS_LOCK)
        if DOWNLOADS_CACHE_PATH.exists():
            shutil.rmtree(DOWNLOADS_CACHE_PATH)
            logging.info("Removed `%s`", DOWNLOADS_CACHE_PATH)

    DOWNLOADS_CACHE_PATH.mkdir(exist_ok=True)
    logging.info("Created `%s`", DOWNLOADS_CACHE_PATH)

    downloads_section_list = parse_downloads_toml()
    downloads_lock_list = parse_downloads_lock()
    github_token = get_github_token()
    download_all(downloads_section_list, downloads_lock_list, github_token)
    save_downloads_lock(downloads_lock_list)

    if cli_args.mariko:
        move_file(
            ROOT_SAVE_PATH,
            r"hekate_ctcaer_(?:\d+\.\d+\.\d+)\.bin",
            ROOT_SAVE_PATH,
            "payload.bin",
        )
        remove_from_root(["switch/reboot_to_payload.nro"])
    else:
        pc_payloads_path = PC_SAVE_PATH / "payloads"
        pc_payloads_path.mkdir(exist_ok=True)
        move_file(
            ROOT_SAVE_PATH, r"hekate_ctcaer_(?:\d+\.\d+\.\d+)\.bin", pc_payloads_path
        )

    move_nro_apps_into_folders()

    if not cli_args.no_config:
        config_files_path: Path = BASE_PATH / "config_files"

        if config_files_path.exists():
            shutil.copytree(config_files_path, ROOT_SAVE_PATH, dirs_exist_ok=True)
            logging.info("Copied `%s` to `%s`", config_files_path, ROOT_SAVE_PATH)

    if cli_args.pack is not None:
        shutil.make_archive(cli_args.pack, "zip", ROOT_SAVE_PATH)
        logging.info(
            "The directory `%s` has been packed into `%s.zip`",
            ROOT_SAVE_PATH,
            cli_args.pack,
        )


if __name__ == "__main__":
    main()
