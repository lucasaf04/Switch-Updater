from pathlib import Path
from tempfile import mkdtemp
from typing import Dict

from SectionId import SectionId

BASE_PATH: Path = Path.cwd()
DOWNLOADS_TOML: Path = BASE_PATH / "downloads.toml"
DOWNLOADS_LOCK: Path = BASE_PATH / "downloads.lock"
DOWNLOADS_CACHE_PATH: Path = BASE_PATH / "downloads_cache"
DOWNLOADS_TEMP_PATH: Path = Path(mkdtemp())
GITHUB_TOKEN: Path = BASE_PATH / "github.token"
ROOT_SAVE_PATH: Path = BASE_PATH / "sd"
SAVE_PATHS: Dict[SectionId, Path] = {
    SectionId.BOOTLOADER: ROOT_SAVE_PATH,
    SectionId.FIRMWARE: ROOT_SAVE_PATH,
    SectionId.PAYLOAD: ROOT_SAVE_PATH / "bootloader/payloads",
    SectionId.NRO_APP: ROOT_SAVE_PATH / "switch",
    SectionId.ATMOSPHERE_MODULE: ROOT_SAVE_PATH / "atmosphere/contents",
    SectionId.OVERLAY: ROOT_SAVE_PATH / "switch/.overlays",
    SectionId.TEGRAEXPLORER_SCRIPT: ROOT_SAVE_PATH / "tegraexplorer/scripts",
}
PC_SAVE_PATH: Path = BASE_PATH / "pc"
