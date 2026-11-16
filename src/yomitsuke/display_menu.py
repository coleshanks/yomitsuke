"""Tools > yomitsuke Card Display: put the display into note types, change it, update it, take it out.

The template work is in templates.py; this is the window, the one-step undo, and the offer to
update note types when a new version of the add-on brings a new display.
"""

from collections.abc import Callable

from anki.collection import Collection, OpChanges
from aqt import mw
from aqt.operations import CollectionOp
from aqt.qt import (
    QAbstractItemView,
    QAction,
    QCheckBox,
    QComboBox,
    QDialog,
    QFont,
    QFontDatabase,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    Qt,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from aqt.utils import askUser, disable_help_button, restoreGeom, saveGeom, showWarning, tooltip

from . import templates

TITLE = "yomitsuke Card Display"
MODE_LABELS = {"": "off", "plain": "plain", "reading": "furigana", "colored": "coloured"}
STATUS = {"current": "", "old": "update available", "none": ""}  # set up: bold; only an update is spelled out
DEFAULTS = {"front": "plain", "back": "reading"}  # what ticking a field fills in
FIELD, JAPANESE, FRONT, BACK = range(4)


def setup(config: Callable[[], dict], save_config: Callable[[dict], None]) -> None:
    action = QAction(f"{TITLE}...", mw)
    action.triggered.connect(lambda: DisplayDialog(mw).show())
    mw.form.menuTools.addAction(action)

    def offer() -> None:
        _offer_update(config, save_config)

    from aqt import gui_hooks

    gui_hooks.profile_did_open.append(lambda: mw.progress.single_shot(1000, offer, False))


def _save(parent: QWidget, notetypes: list[dict], label: str, done: Callable[[], None]) -> None:
    """Write the changed note types as one undo step."""

    def op(col: Collection) -> OpChanges:
        undo = col.add_custom_undo_entry(label)
        for notetype in notetypes:
            col.models.update_dict(notetype)
        return col.merge_undo_entries(undo)

    def failed(err: Exception) -> None:
        showWarning(f"yomitsuke couldn't change the note type:\n\n{err}", parent=parent)

    CollectionOp(parent, op).success(lambda _: done()).failure(failed).run_in_background()


def _outdated() -> list[dict]:
    notetypes = (mw.col.models.get(n.id) for n in mw.col.models.all_names_and_ids())
    return [nt for nt in notetypes if nt and templates.read(nt).display == "old"]


# Asked once per new display
##########################################################################


def _offer_update(config: Callable[[], dict], save_config: Callable[[dict], None]) -> None:
    if not mw.col:
        return
    outdated = _outdated()
    conf = config()
    if not outdated or conf.get("display_offered") == templates.version():
        return
    save_config({**conf, "display_offered": templates.version()})  # asked once, whatever the answer
    names = ", ".join(nt["name"] for nt in outdated)
    count = f"{len(outdated)} note type{'s' if len(outdated) != 1 else ''}"
    question = (
        f"yomitsuke's card display has a new version.\n\nUpdate it in {count}? ({names})\n\n"
        "Only the display script changes: your fields, their setup and the rest of the templates "
        "stay as they are, and Edit > Undo reverses it. You can also do it later from "
        f"Tools > {TITLE}."
    )
    if askUser(question, parent=mw, title="yomitsuke"):
        updated = [templates.update_display(nt) for nt in outdated]
        _save(mw, updated, "Update yomitsuke Display", lambda: tooltip(f"Card display updated in {count}."))


# The window
##########################################################################


class DisplayDialog(QDialog):
    """Note types on the left; on the right, how the chosen one shows its fields."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setWindowTitle(TITLE)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        disable_help_button(self)
        self.notetype: dict | None = None
        self.setup = templates.Setup()

        self.types = QListWidget()
        self.types.currentItemChanged.connect(lambda item, _: self._choose(item))

        self.heading = QLabel()
        self.heading.setWordWrap(True)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Field", "Japanese", "Front", "Back"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(FIELD, QHeaderView.ResizeMode.Stretch)
        for column in (JAPANESE, FRONT, BACK):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        self.note = QLabel()
        self.note.setWordWrap(True)
        self.changes = QPlainTextEdit()
        self.changes.setReadOnly(True)
        self.changes.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))

        self.apply_button = QPushButton("Apply")
        self.apply_button.clicked.connect(self._apply)
        self.remove_button = QPushButton("Remove")
        self.remove_button.clicked.connect(self._remove)
        self.update_button = QPushButton("Update All")
        self.update_button.setToolTip("Put the current display into every note type that has an older one")
        self.update_button.clicked.connect(self._update_all)
        close = QPushButton("Close")
        close.clicked.connect(self.close)

        right = QWidget()
        side = QVBoxLayout(right)
        side.setContentsMargins(0, 0, 0, 0)
        side.addWidget(self.heading)
        side.addWidget(self.table, 3)
        side.addWidget(self.note)
        side.addWidget(QLabel("Changes to the templates:"))
        side.addWidget(self.changes, 2)
        split = QSplitter()
        split.addWidget(self.types)
        split.addWidget(right)
        split.setStretchFactor(1, 1)
        split.setSizes([220, 560])

        buttons = QHBoxLayout()
        buttons.addWidget(self.update_button)
        buttons.addStretch()
        buttons.addWidget(self.remove_button)
        buttons.addWidget(self.apply_button)
        buttons.addWidget(close)
        layout = QVBoxLayout(self)
        intro = QLabel(
            "Choose which fields hold Japanese and how each side shows them. Only the templates "
            "change, never your notes, and Edit > Undo reverses it."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)
        layout.addWidget(split, 1)
        layout.addLayout(buttons)

        self.resize(820, 560)
        restoreGeom(self, "yomitsuke-display")
        self._fill_types()

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt's name)
        saveGeom(self, "yomitsuke-display")
        super().closeEvent(event)

    # The list of note types

    def _fill_types(self, keep: int | None = None) -> None:
        self.types.blockSignals(True)
        self.types.clear()
        chosen = None
        for entry in mw.col.models.all_names_and_ids():
            notetype = mw.col.models.get(entry.id)
            display = templates.read(notetype).display
            status = STATUS[display]
            item = QListWidgetItem(f"{entry.name}    ({status})" if status else entry.name)
            item.setData(Qt.ItemDataRole.UserRole, entry.id)
            if display != "none":
                font = QFont(item.font())
                font.setBold(True)
                item.setFont(font)
            self.types.addItem(item)
            if entry.id == keep or (keep is None and chosen is None and display != "none"):
                chosen = item
        self.types.blockSignals(False)
        self.update_button.setVisible(bool(_outdated()))  # only there when something needs it
        self.types.setCurrentItem(chosen or self.types.item(0))

    def _choose(self, item: QListWidgetItem | None) -> None:
        if item is None:
            return
        self.notetype = mw.col.models.get(item.data(Qt.ItemDataRole.UserRole))
        self.setup = templates.read(self.notetype)
        self._fill_table()

    # The table for one note type

    def _fill_table(self) -> None:
        setup = self.setup
        name = self.notetype["name"]
        status = {"current": "has the display", "old": "has an older display", "none": "doesn't have the display yet"}
        self.heading.setText(f"<b>{name}</b> {status[setup.display]}.")
        rows = setup.fields + list(setup.filtered)
        self.table.setRowCount(0)  # drops the last note type's widgets, which setItem would leave
        self.table.setRowCount(len(rows))
        for row, field in enumerate(rows):
            self.table.setItem(row, FIELD, QTableWidgetItem(field))
            if field in setup.filtered:
                self._unavailable(row, f"shown with Anki's {{{{{setup.filtered[field]}:}}}}")
                continue
            modes = setup.modes.get(field, {})
            tick = QCheckBox()
            tick.setChecked(bool(modes))
            tick.toggled.connect(lambda on, r=row: self._tick(r, on))
            self.table.setCellWidget(row, JAPANESE, _centred(tick))
            for column, side in ((FRONT, "front"), (BACK, "back")):
                if side not in setup.sides[field]:
                    self.table.setItem(row, column, _grey_item("not on this side"))
                    continue
                box = QComboBox()
                for mode, label in MODE_LABELS.items():
                    box.addItem(label, mode)
                box.setCurrentIndex(box.findData(modes.get(side, "")))
                box.setEnabled(bool(modes))
                box.currentIndexChanged.connect(self._refresh)
                self.table.setCellWidget(row, column, box)
        if not rows:
            self.note.setText("This note type's templates don't show any fields directly.")
        elif setup.filtered:
            self.note.setText(
                "Fields shown through Anki's own filters, like {{furigana:Field}}, are left as they are: "
                "the two would fight. To use yomitsuke's display for one, put it in the template as "
                "plain {{Field}} first."
            )
        else:
            self.note.setText("")
        self.remove_button.setEnabled(setup.display != "none" or bool(setup.modes))
        self._refresh()

    def _unavailable(self, row: int, why: str) -> None:
        for column in (JAPANESE, FRONT, BACK):
            self.table.setItem(row, column, _grey_item(why if column == JAPANESE else ""))

    def _box(self, row: int, column: int) -> QComboBox | None:
        widget = self.table.cellWidget(row, column)
        return widget if isinstance(widget, QComboBox) else None

    def _tick(self, row: int, on: bool) -> None:
        for column, side in ((FRONT, "front"), (BACK, "back")):
            box = self._box(row, column)
            if box:
                box.blockSignals(True)
                box.setCurrentIndex(box.findData(DEFAULTS[side] if on else ""))
                box.setEnabled(on)
                box.blockSignals(False)
        self._refresh()

    def chosen(self) -> dict[str, dict[str, str]]:
        """field -> side -> mode, from the table."""
        out: dict[str, dict[str, str]] = {}
        for row in range(self.table.rowCount()):
            field = self.table.item(row, FIELD).text()
            for column, side in ((FRONT, "front"), (BACK, "back")):
                box = self._box(row, column)
                if box and box.isEnabled() and box.currentData():
                    out.setdefault(field, {})[side] = box.currentData()
        return out

    def _proposed(self) -> dict:
        new = templates.apply(self.notetype, self.chosen())
        # An older display is brought up to date along with any change.
        return templates.update_display(new)

    def _refresh(self) -> None:
        if self.notetype is None:
            return
        text = templates.changes(self.notetype, self._proposed())
        self.changes.setPlainText(text or "No changes.")
        self.apply_button.setEnabled(bool(text))

    # Buttons

    def _done(self, message: str) -> None:
        tooltip(message, parent=self)
        self._fill_types(keep=self.notetype["id"])

    def _apply(self) -> None:
        new = self._proposed()
        if new == self.notetype:
            return
        name = new["name"]
        _save(self, [new], "yomitsuke Card Display", lambda: self._done(f"{name}: card display changed."))

    def _remove(self) -> None:
        name = self.notetype["name"]
        question = (
            f"Take yomitsuke's display out of {name}?\n\nEvery field goes back to plain {{{{Field}}}} in the "
            "templates and the display script is removed. Your notes keep their readings, which will show "
            "as raw [brackets] until a display is added again. Edit > Undo reverses this."
        )
        if askUser(question, parent=self, title="yomitsuke"):
            new = templates.remove(self.notetype)
            _save(self, [new], "Remove yomitsuke Display", lambda: self._done(f"{name}: card display removed."))

    def _update_all(self) -> None:
        outdated = _outdated()
        if outdated:
            updated = [templates.update_display(nt) for nt in outdated]
            count = f"{len(updated)} note type{'s' if len(updated) != 1 else ''}"
            _save(self, updated, "Update yomitsuke Display", lambda: self._done(f"Card display updated in {count}."))


def _centred(widget: QWidget) -> QWidget:
    holder = QWidget()
    layout = QHBoxLayout(holder)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(widget, alignment=Qt.AlignmentFlag.AlignCenter)
    return holder


def _grey_item(text: str) -> QTableWidgetItem:
    item = QTableWidgetItem(text)
    item.setFlags(Qt.ItemFlag.NoItemFlags)
    return item
