from enum import Enum, auto


class SectionId(Enum):
    BOOTLOADER = auto()
    FIRMWARE = auto()
    PAYLOAD = auto()
    NRO_APP = auto()
    ATMOSPHERE_MODULE = auto()
    OVERLAY = auto()
    TEGRAEXPLORER_SCRIPT = auto()


_nameToSectionId = {
    "bootloader": SectionId.BOOTLOADER,
    "firmware": SectionId.FIRMWARE,
    "payload": SectionId.PAYLOAD,
    "nro_app": SectionId.NRO_APP,
    "atmosphere_module": SectionId.ATMOSPHERE_MODULE,
    "overlay": SectionId.OVERLAY,
    "tegraexplorer_script": SectionId.TEGRAEXPLORER_SCRIPT,
}


def getSectionId(section_name: str):
    result = _nameToSectionId.get(section_name)
    if result is None:
        raise RuntimeError(f"Unsupported section name: `{section_name}`")
    return result
