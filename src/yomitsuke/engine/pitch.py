"""Turn UniDic's accent number into the pitch code the card templates read.

The codes:
    h   heiban: no drop (accent 0)
    a   atamadaka: drop after the first mora (accent 1)
    o   odaka: drop after the last mora (accent equals the mora count)
    nN  nakadaka: drop after mora N, somewhere in the middle
    kN  kifuku: a verb or adjective with a drop after mora N
"""

from .kana import mora_count

INFLECTING = {"動詞", "形容詞"}


def first_accent(a_type: str | None) -> int | None:
    """UniDic lists one or more accents ("3,0"); only the first is used."""
    if not a_type:
        return None
    first = a_type.split(",")[0].strip()
    return int(first) if first.isdigit() else None


def pitch_code(accent: int | None, reading: str, pos: str) -> str:
    """The code for a word, or "" when the accent is unknown."""
    if accent is None:
        return ""
    if pos in INFLECTING:
        return "h" if accent == 0 else f"k{accent}"
    if accent == 0:
        return "h"
    morae = mora_count(reading)
    if morae and accent >= morae:
        return "o"
    if accent == 1:
        return "a"
    return f"n{accent}"
