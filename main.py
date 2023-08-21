import logging
import re
import shutil
from argparse import ArgumentParser, ArgumentTypeError
from pathlib import Path
from typing import List, Optional
from zipfile import ZipFile

from Config import (
    BASE_PATH,
    DOWNLOADS_LOCK,
    ROOT_SAVE_PATH,
    SAVE_PATHS,
    get_github_token,
    parse_downloads_lock,
    parse_downloads_toml,
    save_downloads_lock,
)
from Downloader import DOWNLOADS_TEMP_PATH, DownloaderLock
from Section import Section, SectionId


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


def create_payload() -> None:
    for file in ROOT_SAVE_PATH.iterdir():
        if re.search(r"hekate_ctcaer_(?:\d+\.\d+\.\d+)\.bin", file.name) is not None:
            new_path = file.with_name("payload.bin")
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
    for item in SAVE_PATHS[SectionId.NRO_APPS].iterdir():
        if item.is_file() and item.suffix == ".nro":
            folder = item.parent / item.stem
            folder.mkdir(exist_ok=True)
            item.rename(folder / item.name)


def valid_log_level(level: str) -> str:
    numeric_level = getattr(logging, level.upper(), None)
    if not isinstance(numeric_level, int):
        raise ArgumentTypeError(f"Invalid log level: `{level}`")
    return level


def main() -> None:
    valid_log_levels = logging.getLevelNamesMapping().keys()

    cli_parser = ArgumentParser()
    cli_parser.add_argument(
        "--log",
        type=valid_log_level,
        default="ERROR",
        help=f"Set the log level: {', '.join(valid_log_levels)} (default ERROR)",
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
