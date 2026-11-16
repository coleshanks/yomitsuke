"""Small helpers for telling scripts apart and converting katakana to hiragana."""

import re

_KATA_TO_HIRA = {code: code - 0x60 for code in range(ord("ァ"), ord("ヶ") + 1)}

KANJI = re.compile(r"[㐀-䶿一-鿿豈-﫿々〆ヵヶ]")
JAPANESE = re.compile(r"[぀-ヿ㐀-䶿一-鿿豈-﫿々〆ー]")
_SMALL = set("ゃゅょぁぃぅぇぉゎャュョァィゥェォヮ")


def to_hiragana(text: str) -> str:
    return text.translate(_KATA_TO_HIRA)


def has_kanji(text: str) -> bool:
    return KANJI.search(text) is not None


def mora_count(reading: str) -> int:
    """Morae in a kana reading: small ゃゅょ etc. join the kana before them."""
    return sum(1 for ch in reading if ch not in _SMALL)
