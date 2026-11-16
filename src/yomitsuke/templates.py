"""yomitsuke's card display in a note type's templates: read how it's set up, and change it.

Plain Python with no Anki, so it can be tested on its own. A note type is Anki's dict, with
"flds" (each with a "name") and "tmpls" (each with "qfmt", the front, and "afmt", the back).

yomitsuke only ever adds, changes or removes two things in a template:

- a wrapper round a field, which tells the display how to show it:
      <span class="ym" data-mode="reading">{{Sentence}}</span>
  New wrappers are inline <span>s, so the layout doesn't move. A <div> wrapper someone already
  has keeps its tag.
- the display itself, one <script> block between BEGIN and END at the end of each side.

Everything else is left exactly as it is: other markup and styling, {{FrontSide}}, conditionals,
fields inside attributes, comments and scripts, and fields shown through Anki's own filters
such as {{furigana:Sentence}}, which would fight with the display.
"""

import copy
import difflib
import hashlib
import json
import re
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path

DISPLAY = Path(__file__).resolve().parent / "display"

NAME = "yomitsuke"
# Names the add-on had before, whose display blocks are still in people's templates. They're
# recognised as an older display, so the update offer swaps them for the current one.
# tools/rename.py adds the old name here.
PAST_NAMES: tuple[str, ...] = ()

BEGIN, END = f"<!-- {NAME} display -->", f"<!-- /{NAME} display -->"

MODES = ("plain", "reading", "colored")
SIDES = {"front": "qfmt", "back": "afmt"}


def _block_pattern(names: tuple[str, ...]) -> re.Pattern:
    either = "|".join(rf"<!-- {re.escape(n)} display -->.*?<!-- /{re.escape(n)} display -->" for n in names)
    return re.compile(f"(?:{either})", re.S)


_BLOCK = _block_pattern((NAME, *PAST_NAMES))
_BLOCK_AT_END = re.compile(r"\s*" + _BLOCK.pattern + r"\s*$", re.S)

# One pass over a template, left to right. Comments, scripts, styles and tags are matched first
# so a field inside them (<img src="{{Picture}}">) is never touched.
_TOKEN = re.compile(
    r"(?P<comment><!--.*?-->)"
    r"|(?P<code><(?P<code_tag>script|style)\b.*?</(?P=code_tag)\s*>)"
    r"|(?P<wrapper><(?P<tag>div|span) class=\"ym\" data-mode=\"(?P<mode>[a-z]*)\">"
    r"\s*(?P<inner>\{\{[^{}]*\}\})\s*</(?P=tag)>)"
    r"|(?P<ref>\{\{[^{}]*\}\})"
    r"|(?P<markup><[^>]*>)",
    re.S | re.I,
)


@cache
def snippet() -> str:
    """The display: the script with its CSS inside, as one block for the end of a template."""
    js = (DISPLAY / "yomitsuke.js").read_text(encoding="utf-8")
    css = (DISPLAY / "yomitsuke.css").read_text(encoding="utf-8")
    css_literal = json.dumps(css, ensure_ascii=False).replace("</", "<\\/")  # </...> can't end the script
    js = js.replace('"/*CSS*/"', css_literal)
    # Anki rewrites these anywhere in a template, scripts included, which breaks the script.
    for bad in ("{{", "}}", "[sound:", "[anki:"):
        if bad in js:
            raise ValueError(f"the display script can't contain {bad!r}: Anki would rewrite it")
    return f"{BEGIN}\n<script>\n{js}</script>\n{END}"


def version() -> str:
    """A short fingerprint of the display, to tell when it has changed."""
    return hashlib.sha256(snippet().encode()).hexdigest()[:12]


def _parse_ref(ref: str) -> tuple[str, str]:
    """{{furigana:Sentence}} -> ("Sentence", "furigana"); {{Sentence}} -> ("Sentence", "")."""
    inside = ref[2:-2].strip()
    if ":" in inside:
        filters, name = inside.rsplit(":", 1)
        return name.strip(), filters.strip()
    return inside, ""


@dataclass
class Setup:
    """How a note type's templates show its fields, as far as yomitsuke is concerned."""

    fields: list[str] = field(default_factory=list)
    """Fields the templates show directly, in the note type's order: the ones that can be set up."""
    sides: dict[str, set[str]] = field(default_factory=dict)
    """The sides ("front", "back") each of those fields is on."""
    modes: dict[str, dict[str, str]] = field(default_factory=dict)
    """field -> side -> mode, for the fields yomitsuke shows. A side that's missing is off."""
    filtered: dict[str, str] = field(default_factory=dict)
    """Fields shown only through one of Anki's filters, with the filter: left alone."""
    display: str = "none"
    """The display block: "none", "current", or "old" (a different version)."""

    def japanese(self) -> list[str]:
        """The fields set up for the display, in the note type's order."""
        return [name for name in self.fields if self.modes.get(name)]


def field_names(notetype: dict) -> list[str]:
    return [f["name"] for f in notetype["flds"]]


def read(notetype: dict) -> Setup:
    names = field_names(notetype)
    setup = Setup()
    blocks = []
    for tmpl in notetype["tmpls"]:
        for side, key in SIDES.items():
            html = tmpl[key]
            blocks += _BLOCK.findall(html)
            for m in _TOKEN.finditer(_BLOCK.sub("", html)):
                if m["wrapper"] or m["ref"]:
                    name, filters = _parse_ref(m["inner"] or m["ref"])
                    if name not in names:
                        continue  # {{FrontSide}}, {{Tags}}, {{#Field}}...
                    if filters:
                        setup.filtered.setdefault(name, filters)
                        continue
                    setup.sides.setdefault(name, set()).add(side)
                    if m["wrapper"] and m["mode"] in MODES:
                        setup.modes.setdefault(name, {}).setdefault(side, m["mode"])
    setup.fields = [name for name in names if name in setup.sides]
    setup.filtered = {name: f for name, f in setup.filtered.items() if name not in setup.sides}
    if blocks:
        setup.display = "current" if all(b == snippet() for b in blocks) else "old"
    return setup


def apply(notetype: dict, modes: dict[str, dict[str, str]]) -> dict:
    """A copy of the note type with its templates showing each field as modes says.

    modes is field -> side -> mode; a field or side that's missing is off. Each field shown on a
    side gets that side's mode, a field that's now off is unwrapped back to plain {{Field}}, and
    the display goes at the end of each side, or comes out when nothing is left for it to show.
    """
    names = set(field_names(notetype))
    showing = any(mode for sides in modes.values() for mode in sides.values())
    new = copy.deepcopy(notetype)
    for tmpl in new["tmpls"]:
        for side, key in SIDES.items():
            html = _rewrite(tmpl[key], side, names, modes)
            tmpl[key] = _with_display(html) if showing else _without_display(html)
    return new


def remove(notetype: dict) -> dict:
    """A copy of the note type with yomitsuke taken out entirely."""
    return apply(notetype, {})


def update_display(notetype: dict) -> dict:
    """A copy of the note type with the current display in place of an older one. Nothing else changes."""
    new = copy.deepcopy(notetype)
    for tmpl in new["tmpls"]:
        for key in SIDES.values():
            if _BLOCK.search(tmpl[key]):
                tmpl[key] = _with_display(tmpl[key])
    return new


def _rewrite(html: str, side: str, names: set[str], modes: dict[str, dict[str, str]]) -> str:
    # The display block is a comment and a script, so the tokens step over it untouched.
    def one(m: re.Match) -> str:
        if not (m["wrapper"] or m["ref"]):
            return m[0]
        ref = m["inner"] or m["ref"]
        name, filters = _parse_ref(ref)
        if name not in names or filters:
            return m[0]
        want = modes.get(name, {}).get(side)
        if m["wrapper"]:
            if not want:
                return ref
            if want == m["mode"]:
                return m[0]
            return f'<{m["tag"]} class="ym" data-mode="{want}">{ref}</{m["tag"]}>'
        if want:
            return f'<span class="ym" data-mode="{want}">{ref}</span>'
        return m[0]

    return _TOKEN.sub(one, html)


def _with_display(html: str) -> str:
    if _BLOCK.search(html):
        return _BLOCK.sub(lambda _: snippet(), html, count=1)
    return html + "\n" + snippet() + "\n"  # exactly what _without_display takes off again


def _without_display(html: str) -> str:
    m = _BLOCK.search(html)
    if not m:
        return html
    added = "\n" + m[0] + "\n"
    if html.endswith(added):  # where _with_display put it: back to the template as it was
        return html[: -len(added)]
    # Put there some other way: at the end, the gap before it goes too; elsewhere just the block.
    return _BLOCK.sub("", _BLOCK_AT_END.sub("", html))


def changes(old: dict, new: dict) -> str:
    """What apply() would change, line by line, with the display script shortened to one line."""

    def lines(html: str) -> list[str]:
        return _BLOCK.sub("<!-- yomitsuke display (script) -->", html).splitlines()

    out = []
    for before, after in zip(old["tmpls"], new["tmpls"]):
        for side, key in SIDES.items():
            diff = list(difflib.unified_diff(lines(before[key]), lines(after[key]), lineterm="", n=0))
            if diff:
                out.append(f"{before['name']}, {side}:")
                out += [line for line in diff[2:] if not line.startswith("@@")]
            old_blocks, new_blocks = _BLOCK.findall(before[key]), _BLOCK.findall(after[key])
            if old_blocks and new_blocks and old_blocks != new_blocks:
                out.append(f"{before['name']}, {side}: the display script is updated")
    return "\n".join(out)
