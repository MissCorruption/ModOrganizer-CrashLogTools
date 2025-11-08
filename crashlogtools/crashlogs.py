import configparser
import ctypes.wintypes
from pathlib import Path
from typing import Set, Optional, Sequence, Union

from mobase import IOrganizer

CSIDL_PERSONAL = 5
SHGFP_TYPE_CURRENT = 0


class CrashLogFinder:
    def __init__(self, log_directory: Union[str, Path], a_filter: str):
        self.log_directory = log_directory
        self.filter = a_filter

    @property
    def log_directory(self) -> Path:
        return self._log_directory

    @log_directory.setter
    def log_directory(self, value: Union[str, Path]) -> None:
        a_value = Path(value).resolve()
        if a_value.is_dir():
            self._log_directory = a_value
        if not a_value.exists():
            a_value.mkdir(parents=True, exist_ok=True)

    def get_crash_log_dir(self, organizer: IOrganizer) -> Path:
        results: Sequence[str] = organizer.findFiles('SKSE/Plugins/', 'CrashLogger.ini')

        result: Optional[str] = results[0] if len(results) > 0 else None

        if result is None:
            return self.log_directory

        with open(result, 'r', encoding='utf-8-sig') as f:  # file says UTF_8_BOM
            config = configparser.ConfigParser()
            config.read_file(f)

        log_dir: Optional[str] = config.get('Debug', 'Crashlog Directory', fallback=None)

        if log_dir in (None, ''):
            return self.log_directory

        crash_log_dir: Path = Path(log_dir).resolve()

        if not crash_log_dir.is_dir():
            return self.log_directory

        if not crash_log_dir.exists():
            crash_log_dir.mkdir(parents=True, exist_ok=True)

        return crash_log_dir

    def get_crash_logs(self, organizer: IOrganizer) -> Set[Path]:
        return set(self.get_crash_log_dir(organizer).glob(self.filter))


def get_documents_path() -> str:
    buf = ctypes.create_unicode_buffer(ctypes.wintypes.MAX_PATH)
    # noinspection PyUnresolvedReferences
    ctypes.windll.shell32.SHGetFolderPathW(
        None, CSIDL_PERSONAL, None, SHGFP_TYPE_CURRENT, buf
    )
    return buf.value


MY_DOCUMENTS = Path(get_documents_path())

FINDERS = {
    "Skyrim Special Edition": CrashLogFinder(
        MY_DOCUMENTS / "My Games" / "Skyrim Special Edition" / "SKSE",
        "crash-*.log",
    ),
    "Skyrim VR": CrashLogFinder(
        MY_DOCUMENTS / "My Games" / "Skyrim VR" / "SKSE", "crash-*.log"
    ),
}


def supported_games() -> Set[str]:
    return set(FINDERS.keys())


def get_finder(game: str) -> Optional[CrashLogFinder]:
    return FINDERS.get(game)
