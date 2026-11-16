"""The Anki side: a browser menu item, a dialog to pick fields, and one undoable change."""

from collections.abc import Sequence
from pathlib import Path

from anki.collection import Collection, OpChanges
from anki.notes import NoteId
from aqt import gui_hooks, mw
from aqt.browser import Browser
from aqt.operations import CollectionOp
from aqt.qt import (
    QAction,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QLabel,
    QMenu,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)
from aqt.utils import showWarning, tooltip

from . import display_menu, engine, templates

ACTION = "Add Readings (yomitsuke)..."
PREVIEW_NOTES = 3
MY_READINGS_HEADER = """\
# Your own reading fixes for yomitsuke. These win over everything else.
# One word per line: word, a tab, the reading, and optionally a tab and a pitch code.
#   私	わたし
#   物	もの	h
# Pitch codes: h (flat), a (drop after the first mora), o (drop after the last),
# n2 n3... (drop after that mora), k1 k2... (verbs and adjectives).
"""


def setup() -> None:
    _load_my_readings()
    gui_hooks.browser_menus_did_init.append(_add_to_notes_menu)
    gui_hooks.browser_will_show_context_menu.append(_add_to_context_menu)
    display_menu.setup(_config, _save_config)


def _user_files() -> Path:
    path = Path(mw.addonManager.addonsFolder(__name__.split(".")[0])) / "user_files"
    path.mkdir(exist_ok=True)
    return path


def _load_my_readings() -> None:
    path = _user_files() / "my-readings.tsv"
    if not path.exists():
        path.write_text(MY_READINGS_HEADER, encoding="utf-8")
    engine.load_fixes(path)


def _config() -> dict:
    return mw.addonManager.getConfig(__name__) or {}


def _save_config(conf: dict) -> None:
    mw.addonManager.writeConfig(__name__, conf)


# Menus
##########################################################################


def _add_to_notes_menu(browser: Browser) -> None:
    action = QAction(ACTION, browser)
    action.triggered.connect(lambda: _open(browser))
    browser.form.menu_Notes.addSeparator()
    browser.form.menu_Notes.addAction(action)


def _add_to_context_menu(browser: Browser, menu: QMenu) -> None:
    menu.addSeparator()
    menu.addAction(ACTION, lambda: _open(browser))


def _open(browser: Browser) -> None:
    nids = list(browser.selected_notes())
    if not nids:
        tooltip("Select some notes first.", parent=browser)
        return
    dialog = FieldsDialog(browser, nids)
    if dialog.exec():
        _save_config({**_config(), "fields": dialog.chosen_by_type(), "redo": dialog.redo.isChecked()})
        _run(browser, nids, dialog.chosen_by_type(), dialog.redo.isChecked())


# The dialog
##########################################################################


class FieldsDialog(QDialog):
    """Tick the fields to fill, see a preview, then go."""

    def __init__(self, parent: QWidget, nids: Sequence[NoteId]) -> None:
        super().__init__(parent)
        self.setWindowTitle("yomitsuke")
        self.col = mw.col
        self.nids = nids
        self.boxes: dict[str, list[QCheckBox]] = {}  # note type id -> its field checkboxes
        conf = _config()
        saved = conf.get("fields", {})

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"Add readings to {len(nids)} selected note{'s' if len(nids) != 1 else ''}."))

        # One group of field checkboxes per note type in the selection.
        types: dict[int, list[NoteId]] = {}
        for nid in nids:
            types.setdefault(self.col.get_note(nid).mid, []).append(nid)
        for mid, members in types.items():
            notetype = self.col.models.get(mid)
            group = QGroupBox(f"{notetype['name']} ({len(members)})")
            inner = QVBoxLayout(group)
            ticked = set(saved.get(str(mid), []))
            self.boxes[str(mid)] = []
            # Once the note type has the card display, only the fields it shows as Japanese.
            names = templates.read(notetype).japanese() or self.col.models.field_names(notetype)
            for name in names:
                box = QCheckBox(name)
                box.setChecked(name in ticked)
                box.toggled.connect(self._refresh_preview)
                inner.addWidget(box)
                self.boxes[str(mid)].append(box)
            if not templates.read(notetype).japanese():
                hint = QLabel(f"All fields are listed. Set up Tools > {display_menu.TITLE} to list only Japanese ones.")
                hint.setWordWrap(True)
                hint.setEnabled(False)  # greyed out
                inner.addWidget(hint)
            layout.addWidget(group)

        self.redo = QCheckBox("Redo fields that already have readings (their old readings and pitch are replaced)")
        self.redo.setChecked(bool(conf.get("redo", False)))
        self.redo.toggled.connect(self._refresh_preview)
        layout.addWidget(self.redo)

        layout.addWidget(QLabel("Preview:"))
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setMinimumSize(560, 200)
        layout.addWidget(self.preview)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Add Readings")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._refresh_preview()

    def chosen_by_type(self) -> dict[str, list[str]]:
        return {mid: [b.text() for b in boxes if b.isChecked()] for mid, boxes in self.boxes.items()}

    def _refresh_preview(self) -> None:
        chosen, redo = self.chosen_by_type(), self.redo.isChecked()
        lines = []
        for nid in self.nids[:PREVIEW_NOTES]:
            note = self.col.get_note(nid)
            for name in chosen.get(str(note.mid), []):
                before = note[name]
                after = new_value(before, redo)
                if after != before:
                    lines.append(f"{name}:\n  {after}")
                elif before.strip():
                    if not engine.has_annotations(before):
                        why = ""
                    elif redo:
                        why = ", redone with the same result"
                    else:
                        why = ", already has readings"
                    lines.append(f"{name}: (unchanged{why})")
            lines.append("")
        self.preview.setPlainText("\n".join(lines).strip() or "Tick the fields to fill.")


# The change
##########################################################################


def new_value(text: str, redo: bool) -> str:
    """What a field becomes. Fields with readings are left alone unless redo is on."""
    if engine.has_annotations(text):
        if not redo:
            return text
        text = engine.strip(text)
    return engine.annotate(text)


def _run(browser: Browser, nids: Sequence[NoteId], chosen: dict[str, list[str]], redo: bool) -> None:
    changed = 0

    def op(col: Collection) -> OpChanges:
        nonlocal changed
        undo = col.add_custom_undo_entry("Add Readings")
        notes = []
        for nid in nids:
            note = col.get_note(nid)
            touched = False
            for name in chosen.get(str(note.mid), []):
                if name in note:
                    value = new_value(note[name], redo)
                    if value != note[name]:
                        note[name] = value
                        touched = True
            if touched:
                notes.append(note)
        if notes:
            col.update_notes(notes)
        changed = len(notes)
        return col.merge_undo_entries(undo)

    def done(_: OpChanges) -> None:
        tooltip(f"Readings added to {changed} note{'s' if changed != 1 else ''}. Edit > Undo reverses it.", parent=browser)

    def failed(err: Exception) -> None:
        showWarning(f"yomitsuke couldn't add readings:\n\n{err}", parent=browser)

    CollectionOp(browser, op).success(done).failure(failed).run_in_background()
