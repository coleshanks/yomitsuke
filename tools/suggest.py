"""Suggest reading fixes: words that notes with readings consistently read differently.

The notes' readings were written by hand or by another tool, so a disagreement is only a
lead. Each suggestion shows whether Kanjium lists the notes' reading and the engine's, as a
second opinion. Good ones go into src/yomitsuke/engine/data/readings.tsv by hand.
Reads the collection read-only.

    uv run python tools/suggest.py <collection.anki2> <note type>... [--min 2]
"""

import argparse
import collections
import difflib
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from score import normalise, notetype_ids, open_collection, parse  # noqa: E402

import yomitsuke.engine as engine  # noqa: E402
from yomitsuke.engine import accents  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("collection")
    ap.add_argument("notetypes", nargs="+", help="the note types whose notes to read")
    ap.add_argument("--min", type=int, default=2, help="seen at least this often in the notes")
    args = ap.parse_args()

    db = open_collection(args.collection)
    mids = notetype_ids(db, args.notetypes)
    card_reads = collections.defaultdict(collections.Counter)
    ours_reads = collections.defaultdict(collections.Counter)
    marks = ", ".join("?" * len(mids))
    for (flds,) in db.execute(f"select flds from notes where mid in ({marks})", mids):
        for field in flds.split("\x1f"):
            card = parse(normalise(field))
            if not card:
                continue
            ours = parse(normalise(engine.annotate(engine.strip(field))))
            sm = difflib.SequenceMatcher(a=[c[0] for c in card], b=[o[0] for o in ours], autojunk=False)
            for block in sm.get_matching_blocks():
                for k in range(block.size):
                    (word, cr, _), (_, orr, _) = card[block.a + k], ours[block.b + k]
                    if cr and orr and re.search(r"[一-鿿]", word):
                        card_reads[word][cr] += 1
                        ours_reads[word][orr] += 1

    rows = []
    for word, reads in card_reads.items():
        cr, seen = reads.most_common(1)[0]
        orr = ours_reads[word].most_common(1)[0][0]
        if cr != orr and seen >= args.min and seen / sum(reads.values()) >= 0.8:
            listed = lambda r: "yes" if accents.lookup(word, r) is not None else "no"  # noqa: E731
            rows.append((seen, word, cr, orr, listed(cr), listed(orr)))
    print("seen  word  notes  engine  (Kanjium lists the notes' / engine's reading)")
    for seen, word, cr, orr, lc, lo in sorted(rows, reverse=True):
        print(f"{seen:4}  {word}  {cr}  {orr}  ({lc} / {lo})")


if __name__ == "__main__":
    main()
