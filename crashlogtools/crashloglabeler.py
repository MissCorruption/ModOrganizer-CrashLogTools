from typing import TYPE_CHECKING, List, Optional

from mobase import (
    IPlugin,
    PluginSetting,
    PluginRequirementFactory,
    ReleaseType,
    VersionInfo,
    IPluginRequirement,
    IOrganizer,
)

try:
    from PyQt5.QtCore import QFile

    if TYPE_CHECKING:
        from PyQt5.QtWidgets import QMainWindow
except ImportError:
    from PyQt6.QtCore import QFile

    if TYPE_CHECKING:
        from PyQt6.QtWidgets import QMainWindow

from .crashlogutil import CrashLogProcessor
from . import crashlogs
from . import addresslib


class CrashLogLabeler(IPlugin):
    def __init__(self):
        super().__init__()
        self.processor: Optional[CrashLogProcessor] = None
        self.finder: Optional[crashlogs.CrashLogFinder] = None
        self.processed_logs = set()
        self.organizer: Optional[IOrganizer] = None

    def name(self) -> str:
        return "Crash Log Labeler"

    def version(self) -> "VersionInfo":
        return VersionInfo(1, 0, 1, 0, ReleaseType.FINAL)

    def description(self) -> str:
        return "Labels known addresses in Skyrim crash logs"

    def author(self) -> str:
        return "Parapets, edited by Miss Corruption"

    def requirements(self) -> List[IPluginRequirement]:
        games = set.intersection(
            addresslib.supported_games(), crashlogs.supported_games()
        )

        return [PluginRequirementFactory.gameDependency(tuple(games))]

    def settings(self) -> List[PluginSetting]:
        return [
            PluginSetting("offline_mode", "Disable update from remote database", True),
        ]

    def init(self, organizer: IOrganizer) -> bool:
        self.organizer = organizer
        organizer.onFinishedRun(self.onFinishedRunCallback)
        organizer.onUserInterfaceInitialized(self.onUserInterfaceInitializedCallback)

        return True

    # noinspection PyUnusedLocal
    def onFinishedRunCallback(self, path: str, exit_code: int):
        new_logs = self.finder.get_crash_logs(self.organizer).difference(self.processed_logs)
        if not new_logs:
            return

        if not self.organizer.pluginSetting(self.name(), "offline_mode"):
            self.processor.update_database()

        for log in new_logs:
            self.processor.process_log(log)

        self.processed_logs.update(new_logs)

    # noinspection PyUnusedLocal
    def onUserInterfaceInitializedCallback(self, main_window: "QMainWindow"):
        game = self.organizer.managedGame().gameName()
        self.finder = crashlogs.get_finder(game)

        if self.finder is None:
            return
        self.processor = CrashLogProcessor(game, lambda file: QFile(str(file)).moveToTrash())

        if not self.organizer.pluginSetting(self.name(), "offline_mode"):
            self.processor.update_database()

        logs = self.finder.get_crash_logs(self.organizer)
        for log in logs:
            self.processor.process_log(log)
        self.processed_logs.update(logs)
