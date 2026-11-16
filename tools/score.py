"""Score the engine against notes that already have readings in the bracket format.

Each annotated field is stripped back to plain text, run through yomitsuke's engine, and
compared word by word with what the note holds. Readings written by hand or by another tool
make a useful reference, though not a perfect one: they have mistakes of their own, which is
why each reading is also checked against the Kanjium dictionary.

Reads the collection read-only; Anki can stay open. Usage:
    uv run python tools/score.py <collection.anki2> <note type> [notes] [--show N]
"""

import argparse
import collections
import difflib
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from yomitsuke.engine import annotate, strip  # noqa: E402
from yomitsuke.engine import accents  # noqa: E402
from yomitsuke.engine.kana import has_kanji, to_hiragana  # noqa: E402

_WORD = re.compile(r"([^ 　&>;\n\[\]]+?)\[([^\]]*)\]([^ 　&<;\n\[\]]*)")
_KANA = re.compile(r"^[぀-ヿー]+$")


def normalise(field: str) -> str:
    """A field with dictionary forms dropped and the first pitch only, so cards and ours compare alike."""

    def fix(m: re.Match) -> str:
        inside = m.group(0)[1:-1]
        if inside.startswith("sound:"):
            return m.group(0)
        reading, _, pitch = inside.partition(";")
        reading = reading.split(",")[0]
        pitch = pitch.split(",")[0]
        return f"[{reading};{pitch}]" if pitch else f"[{reading}]"

    return re.sub(r"\[[^\]]*\]", fix, field)


def parse(field: str) -> list[tuple[str, str, str]]:
    """(word, reading, pitch) for every annotated word."""
    out = []
    for base, inside, tail in _WORD.findall(field):
        if inside.startswith("sound:"):
            continue
        reading, _, pitch = inside.partition(";")
        if not reading and _KANA.match(base):
            reading = base
        out.append((base + tail, to_hiragana(reading + tail) if reading else "", pitch))
    return out


def open_collection(path: str) -> sqlite3.Connection:
    db = sqlite3.connect(f"file:{path}?mode=ro&immutable=1", uri=True)
    db.create_collation("unicase", lambda a, b: 0)
    return db


def notetype_ids(db: sqlite3.Connection, names: list[str]) -> list[int]:
    ids = []
    for name in names:
        row = db.execute("select id from notetypes where name = ? collate binary", (name,)).fetchone()
        if row is None:
            raise SystemExit(f"no note type named {name!r}")
        ids.append(row[0])
    return ids


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("collection")
    ap.add_argument("notetype", help="the note type whose notes to score")
    ap.add_argument("notes", nargs="?", type=int, default=400, help="how many of its newest notes")
    ap.add_argument("--show", type=int, default=0, help="print this many differing fields")
    ap.add_argument("--no-fixes", action="store_true", help="score the engine without the reading fixes")
    args = ap.parse_args()
    if args.no_fixes:
        import yomitsuke.engine as engine

        engine._fixes.clear()

    db = open_collection(args.collection)
    (mid,) = notetype_ids(db, [args.notetype])
    rows = db.execute("select flds from notes where mid=? order by id desc limit ?", (mid, args.notes)).fetchall()

    n = collections.Counter()
    pitch_diffs, read_diffs, shown = collections.Counter(), collections.Counter(), 0
    for (flds,) in rows:
        for field in flds.split("\x1f"):
            card = normalise(field)
            truth = parse(card)
            if not truth:
                continue
            ours_field = normalise(annotate(strip(field)))  # ours carries dictionary forms on k words
            ours = parse(ours_field)
            n["fields"] += 1
            n["card words"] += len(truth)
            n["our words"] += len(ours)
            same = card.replace(" ", "") == ours_field.replace(" ", "")
            n["identical fields"] += same
            if not same and shown < args.show:
                shown += 1
                print("card:", card, "\nours:", ours_field, "\n")
            sm = difflib.SequenceMatcher(a=[t[0] for t in truth], b=[o[0] for o in ours], autojunk=False)
            for block in sm.get_matching_blocks():
                for k in range(block.size):
                    t, o = truth[block.a + k], ours[block.b + k]
                    n["same words"] += 1
                    if t[1] and has_kanji(t[0]) and accents.known(t[0]):
                        # A dictionary check, independent of the notes: is each reading a real one?
                        n["dictionary checked"] += 1
                        n["dictionary: card ok"] += accents.lookup(t[0], t[1]) is not None
                        n["dictionary: ours ok"] += accents.lookup(t[0], o[1]) is not None
                    if t[1]:
                        n["readings compared"] += 1
                        if t[1] == o[1]:
                            n["readings agree"] += 1
                        else:
                            read_diffs[(t[0], t[1], o[1])] += 1
                    if t[2]:
                        n["pitches compared"] += 1
                        if t[2] == o[2]:
                            n["pitches agree"] += 1
                        else:
                            pitch_diffs[(t[0], t[2], o[2] or "-")] += 1

    pct = lambda a, b: f"{100 * n[a] / max(n[b], 1):.1f}%"  # noqa: E731
    print(f"{len(rows)} notes, {n['fields']} annotated fields, {n['card words']} annotated words on the cards")
    print(f"identical fields (ignoring spaces): {pct('identical fields', 'fields')}")
    print(f"same word boundaries:               {pct('same words', 'card words')}  (ours annotated {n['our words']})")
    print(f"readings agree:                     {pct('readings agree', 'readings compared')}")
    print(f"pitch agrees:                       {pct('pitches agree', 'pitches compared')}")
    print(
        f"reading is in the dictionary:       ours {pct('dictionary: ours ok', 'dictionary checked')}, "
        f"cards {pct('dictionary: card ok', 'dictionary checked')}  ({n['dictionary checked']} words Kanjium lists)"
    )
    print("\ncommonest pitch differences (word, card, ours):", pitch_diffs.most_common(20))
    print("\ncommonest reading differences (word, card, ours):", read_diffs.most_common(15))


if __name__ == "__main__":
    main()
