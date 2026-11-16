"""Pitch accents from Kanjium's list, the first choice before UniDic's own accent data.

data/accents.tsv is accents.txt from https://github.com/mifunetoshiro/kanjium, by Uros O.,
licensed CC BY-SA 4.0 (see data/README.md). Each line is word, reading, accents; an
accent can be tagged with a part of speech when it differs by use: "(副)0,(名)3".
"""

import re
from functools import lru_cache
from pathlib import Path

_DATA = Path(__file__).with_name("data") / "accents.tsv"

# Kanjium's part-of-speech tags, as UniDic names them.
_TAGS = {"名": "名詞", "副": "副詞", "代": "代名詞", "形動": "形状詞", "感": "感動詞", "形": "形容詞", "動": "動詞"}
_ITEM = re.compile(r"^(?:\(([^)]*)\))?(\d+)$")


@lru_cache(maxsize=1)
def _table() -> dict[tuple[str, str], str]:
    table = {}
    if _DATA.exists():
        for line in _DATA.read_text(encoding="utf-8").splitlines():
            parts = line.split("\t")
            if len(parts) == 3:
                table.setdefault((parts[0], parts[1]), parts[2])
    return table


@lru_cache(maxsize=1)
def _words() -> frozenset[str]:
    return frozenset(word for word, _ in _table())


@lru_cache(maxsize=1)
def _by_word() -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for word, reading in _table():
        out.setdefault(word, []).append(reading)
    return out


def readings(word: str) -> list[str]:
    """Every reading the list has for the word."""
    return _by_word().get(word, [])


def known(word: str) -> bool:
    """Whether the list has the word under any reading."""
    return word in _words()


_KATAKANA_WORD = re.compile(r"^[ァ-ヺー]+$")


def compound_reading(word: str, joined: str) -> str:
    """The reading to use if the list has word as one entry, else "".

    joined is the reading of the parts put together; it wins when the list agrees with it.
    Katakana words are listed with no reading, so they keep their own.
    """
    listed = readings(word)
    if not listed:
        return ""
    if joined in listed:
        return joined
    if "" in listed and _KATAKANA_WORD.match(word):
        return joined
    return listed[0] if len(listed) == 1 and listed[0] else ""


def lookup(word: str, reading: str, pos: str = "") -> int | None:
    """The first accent listed for this word and reading, preferring one tagged for pos."""
    raw = _table().get((word, reading))
    if raw is None and _KATAKANA_WORD.match(word):
        raw = _table().get((word, ""))  # katakana words are listed with no reading
    if raw is None:
        return None
    first, tag = None, ""
    for item in raw.split(","):
        m = _ITEM.match(item.strip())
        if not m:
            continue
        tag = m.group(1) if m.group(1) is not None else tag  # a tag carries over to the next items
        accent = int(m.group(2))
        if first is None:
            first = accent
        if pos and any(_TAGS.get(t) == pos for t in tag.split(";")):
            return accent
    return first
