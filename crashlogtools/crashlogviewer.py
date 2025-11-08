import os
from pathlib import Path
from typing import List, Callable, Optional, cast

from mobase import IPluginTool, VersionInfo, ReleaseType, PluginRequirementFactory, IPluginRequirement, PluginSetting, \
    IOrganizer

try:
    from PyQt6.QtCore import *
    from PyQt6.QtGui import *
    from PyQt6.QtWidgets import *

    SortOrder = Qt.SortOrder
    SelectionMode = QAbstractItemView.SelectionMode
    ContextMenuPolicy = Qt.ContextMenuPolicy
    StandardButton = QDialogButtonBox.StandardButton
    Orientation = Qt.Orientation
except ImportError:
    from PyQt5.QtCore import *
    from PyQt5.QtGui import *
    from PyQt5.QtWidgets import *

    SortOrder = Qt
    SelectionMode = QAbstractItemView
    ContextMenuPolicy = Qt
    StandardButton = QDialogButtonBox
    Orientation = Qt

from . import crashlogs


class CrashLogViewer(IPluginTool):
    def __init__(self):
        super().__init__()
        self.dialog: Optional[QDialog] = None
        self.finder: Optional[crashlogs.CrashLogFinder] = None
        self.organizer: Optional[IOrganizer] = None

    def name(self) -> str:
        return "Crash Log Viewer"

    def version(self) -> VersionInfo:
        return VersionInfo(1, 0, 0, 0, ReleaseType.FINAL)

    def description(self) -> str:
        return "Lists crash logs"

    def author(self) -> str:
        return "Parapets, edited by Miss Corruption"

    def requirements(self) -> List[IPluginRequirement]:
        return [PluginRequirementFactory.gameDependency(tuple(crashlogs.supported_games()))]

    def settings(self) -> List[PluginSetting]:
        return []

    def displayName(self) -> str:
        return "Crash Log Viewer"

    def tooltip(self) -> str:
        return "View crash logs"

    def icon(self) -> QIcon:
        return QIcon()

    def init(self, organizer: IOrganizer) -> bool:
        self.organizer = organizer
        organizer.onUserInterfaceInitialized(self.onUserInterfaceInitializedCallback)

        return True

    def change_log_directory(self, new_dir: Path):
        """
        Dynamically changes the crash log directory displayed in the dialog.
        """
        if not self.dialog or not self.finder:
            return

        logs_list: QListView = self.dialog.findChild(QListView)
        if not logs_list:
            return

        proxy_model: FileFilterProxyModel = cast(FileFilterProxyModel, logs_list.model())
        if not proxy_model:
            return

        source_model: QFileSystemModel = cast(QFileSystemModel, proxy_model.sourceModel())
        if not source_model:
            return

        # Update the source model with the new directory
        new_dir_str = str(new_dir)
        # noinspection PyUnresolvedReferences
        self.dialog.setWindowTitle(f"Crash Log Viewer - {new_dir_str}")
        source_model.setRootPath(new_dir_str)

        # Update proxy model filter and sort
        proxy_model.setSourceModel(source_model)
        proxy_model.setFilterWildcard(self.finder.filter)
        # noinspection PyTypeChecker
        proxy_model.sort(0, SortOrder.DescendingOrder)

        # Update the view root index
        logs_list.setRootIndex(proxy_model.mapFromSource(source_model.index(new_dir_str)))

    def display(self) -> None:
        # noinspection PyUnresolvedReferences
        if self.dialog is not None:
            log_dir: Path = self.finder.get_crash_log_dir(self.organizer)
            self.change_log_directory(log_dir)
            # noinspection PyUnresolvedReferences
            self.dialog.show()

    def onUserInterfaceInitializedCallback(self, main_window: QMainWindow):
        game = self.organizer.managedGame().gameName()
        self.finder = crashlogs.get_finder(game)
        if not self.finder:
            return
        self.dialog = self.make_dialog(main_window)

    def make_dialog(self, main_window: QMainWindow) -> QDialog:
        log_dir: Path = self.finder.get_crash_log_dir(self.organizer)
        log_dir_str: str = str(log_dir)

        source_model = QFileSystemModel()
        source_model.setRootPath(log_dir_str)

        proxy_model = FileFilterProxyModel()
        proxy_model.setSourceModel(source_model)
        proxy_model.setFilterWildcard(self.finder.filter)
        # noinspection PyTypeChecker
        proxy_model.sort(0, SortOrder.DescendingOrder)

        dialog = QDialog(main_window)
        dialog.setWindowTitle(f"Crash Log Viewer - {log_dir_str}")

        logs_list = QListView(dialog)
        logs_list.setModel(proxy_model)
        logs_list.setRootIndex(proxy_model.mapFromSource(source_model.index(log_dir_str)))
        logs_list.setDragEnabled(True)
        logs_list.setSelectionMode(SelectionMode.ExtendedSelection)

        def open_logs(index: QModelIndex) -> None:
            source_index = proxy_model.mapToSource(index)
            os.startfile(source_model.filePath(source_index))

        def delete(index: QModelIndex) -> None:
            source_index = proxy_model.mapToSource(index)
            QFile(source_model.filePath(source_index)).moveToTrash()

        def for_selected(
                action: Callable[[QModelIndex], None]
        ) -> Callable[[bool], None]:
            # noinspection PyUnusedLocal
            def fn(checked: bool):
                for index in logs_list.selectedIndexes():
                    action(index)

            return fn

        open_action = QAction(logs_list.tr("&Open"), logs_list)
        # noinspection PyUnresolvedReferences
        open_action.triggered.connect(for_selected(open_logs))
        f = open_action.font()
        f.setBold(True)
        open_action.setFont(f)
        logs_list.addAction(open_action)

        delete_action = QAction(logs_list.tr("&Delete"), logs_list)
        # noinspection PyUnresolvedReferences
        delete_action.triggered.connect(for_selected(delete))
        logs_list.addAction(delete_action)
        logs_list.setContextMenuPolicy(ContextMenuPolicy.ActionsContextMenu)
        # noinspection PyUnresolvedReferences
        logs_list.activated.connect(open_logs)

        button_box = QDialogButtonBox(dialog)
        # noinspection PyUnresolvedReferences
        button_box.rejected.connect(dialog.reject)
        button_box.setOrientation(Orientation.Horizontal)
        button_box.setStandardButtons(StandardButton.Close)
        button_box.button(StandardButton.Close).setAutoDefault(False)

        layout = QVBoxLayout()
        layout.addWidget(logs_list)
        layout.addWidget(button_box)
        dialog.setLayout(layout)

        return dialog


class FileFilterProxyModel(QSortFilterProxyModel):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def _sourceModel(self) -> QFileSystemModel:
        return cast(QFileSystemModel, self.sourceModel())

    def filePath(self, index: QModelIndex) -> str:
        return self._sourceModel().filePath(self.mapToSource(index))

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        source_model = self._sourceModel()
        if source_parent == source_model.index(source_model.rootPath()):
            return super().filterAcceptsRow(source_row, source_parent)
        return True
