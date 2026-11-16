"""Every place the add-on's name appears, found fresh each time, and a way to change it.

    uv run python tools/rename.py                         # list every instance
    uv run python tools/rename.py newname                 # what a rename would change
    uv run python tools/rename.py newname --apply         # do it (needs a clean git tree)
    uv run python tools/rename.py newname --japanese 新名 --apply

In the repo the name is found as yomitsuke, Yomitsuke and YOMITSUKE, in text and in file and
folder names, and each form is replaced by the same form of the new name. The Japanese name
(読み付け) is only replaced when --japanese gives a new one.

Kept on purpose: the short "ym" prefix the display uses in templates and CSS (class="ym",
--ym-heiban...). It sits in people's templates and in any colours they've overridden, and
isn't the name anyone sees. The old name is added to PAST_NAMES in templates.py, so display
blocks already in people's templates are still recognised, and the update offer swaps them.

Outside the repo, a rename also needs the steps printed at the end of each run.
"""

import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OLD = "yomitsuke"
OLD_JA = "読み付け"
PAST = re.compile(r"^PAST_NAMES: tuple\[str, \.\.\.\] = \((.*)\)$", re.M)
PAST_FILE = Path("src") / OLD / "templates.py"

OUTSIDE = f"""\
Outside the repo:
  - GitHub: Settings > rename the repository (GitHub redirects the old URL), then
    git remote set-url origin <new url>
  - The local folder the repo is cloned into, if it's named after the add-on
  - Anki: the new name is a new add-on folder, so it installs beside the old one. Install the
    new build, copy user_files/my-readings.tsv across from the old add-on (Tools > Add-ons >
    View Files), tick the fields in Add Readings once, then delete the old add-on. On the next
    start the new one offers to update the display, which swaps the old-named blocks.
  - Any other Anki profile folder or test install with the add-on, the same way
  - AnkiWeb, if it was published under the old name: a new name there means a new listing
"""


def tracked() -> list[Path]:
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return [Path(p) for p in out.splitlines()]


def forms(old: str, new: str) -> dict[str, str]:
    return {old: new.lower(), old.capitalize(): new.capitalize(), old.upper(): new.upper()}


def text_of(path: Path) -> str | None:
    try:
        return (ROOT / path).read_text(encoding="utf-8")
    except (UnicodeDecodeError, FileNotFoundError):
        return None  # binary


def find(names: list[str]) -> dict[Path, list[tuple[int, str]]]:
    pattern = re.compile("|".join(re.escape(n) for n in names))
    found = {}
    for path in tracked():
        text = text_of(path)
        if text is None:
            continue
        hits = [(i, line.strip()) for i, line in enumerate(text.splitlines(), 1) if pattern.search(line)]
        if hits:
            found[path] = hits
    return found


def renamed_text(text: str, path: Path, new: str, new_ja: str | None) -> str:
    table = forms(OLD, new)
    if new_ja:
        table[OLD_JA] = new_ja
    pattern = re.compile("|".join(re.escape(k) for k in table))
    out = pattern.sub(lambda m: table[m[0]], text)
    if path == PAST_FILE:
        # Undo the replacement inside PAST_NAMES, then add the old name to it.
        past = PAST.search(text)
        names = [n.strip().strip("\"'") for n in past[1].split(",") if n.strip()] + [OLD]
        listed = ", ".join(f'"{n}"' for n in names) + ("," if len(names) == 1 else "")
        out = PAST.sub(f"PAST_NAMES: tuple[str, ...] = ({listed})", out)
    return out


def renamed_path(path: Path, new: str) -> Path:
    return Path(*(part.replace(OLD, new.lower()) for part in path.parts))


def listing() -> None:
    found = find([*forms(OLD, OLD), OLD_JA])
    total = sum(len(hits) for hits in found.values())
    paths = [p for p in tracked() if OLD in str(p)]
    print(f"{total} lines in {len(found)} files mention the name:\n")
    for path, hits in sorted(found.items()):
        print(f"{path} ({len(hits)})")
        for number, line in hits:
            print(f"  {number}: {line[:110]}")
    # Each path up to its first part with the name: src/yomitsuke covers everything inside it.
    tops = {Path(*p.parts[: next(i for i, part in enumerate(p.parts) if OLD in part) + 1]) for p in paths}
    print(f"\n{len(paths)} tracked files have it in their path:")
    for top in sorted(tops):
        print(f"  {top}{'/' if (ROOT / top).is_dir() else ''}")
    print("\n" + OUTSIDE)


def rename(new: str, new_ja: str | None, really: bool) -> None:
    if not re.fullmatch(r"[a-z][a-z0-9_]*", new.lower()):
        raise SystemExit("the new name must be letters, digits and underscores: it becomes a Python package")
    changes: Counter[Path] = Counter()
    for path in tracked():
        text = text_of(path)
        if text is not None and (new_text := renamed_text(text, path, new, new_ja)) != text:
            changes[path] = sum(text.count(k) for k in [*forms(OLD, OLD), OLD_JA] if new_ja or k != OLD_JA)
            if really:
                (ROOT / path).write_text(new_text, encoding="utf-8")
    moves = [(p, renamed_path(p, new)) for p in tracked() if OLD in str(p)]

    for path, count in sorted(changes.items()):
        print(f"{'changed' if really else 'would change'}: {path} ({count})")
    for old, moved in moves:
        if really:
            (ROOT / moved).parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(["git", "mv", str(old), str(moved)], cwd=ROOT, check=True)
        print(f"{'moved' if really else 'would move'}: {old} -> {moved}")
    if really:
        for folder in sorted({ROOT / p.parent for p, _ in moves}, key=lambda f: -len(f.parts)):
            if folder.is_dir() and not any(f for f in folder.rglob("*") if f.is_file() and "__pycache__" not in f.parts):
                subprocess.run(["rm", "-rf", str(folder)], check=True)  # left with only bytecode
        print(f"\n{OLD} added to PAST_NAMES in {renamed_path(PAST_FILE, new)}. Next: uv lock, uv run pytest.")
    else:
        print("\nNothing changed. Add --apply to do it.")
    print("\n" + OUTSIDE)


def main() -> None:
    args = sys.argv[1:]
    really = "--apply" in args
    new_ja = None
    if "--japanese" in args:
        new_ja = args[args.index("--japanese") + 1]
        args.remove(new_ja)
    args = [a for a in args if not a.startswith("--")]
    if not args:
        listing()
        return
    if really:
        dirty = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True).stdout
        if dirty.strip():
            raise SystemExit("commit or stash your changes first, so the rename can be looked at and undone on its own")
    rename(args[0], new_ja, really)


if __name__ == "__main__":
    main()
