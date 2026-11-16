"""Write furigana and pitch codes into a field, in the format the card templates read.

    annotate("時として狂気に陥る人すらいました")
    -> "時[とき;o] と し て 狂気[きょうき;a] に 陥[おちい;k3]る 人[ひと;h] すら いました"

Each word is written as base[reading;pitch]tail: the reading covers the kanji, kana
the word ends with stay outside the brackets, and words are separated by spaces.
Kana-only words get just a pitch code (こと[;o]); particles and punctuation stay bare.
Verbs and adjectives with a drop also carry their dictionary form, 追[お,おいかける;k4]いかけたい,
because the template draws their pitch graph from it.

Nothing outside the text is changed: HTML tags such as <b>, [sound:...] tags, HTML
entities and any existing brackets pass through untouched. Text runs across inline tags
(<b>, <i>, <span>...) are read as one sentence, with the tag as a word boundary; block
tags (<br>, <div>), whitespace and markers such as ① or Ⓐ separate the text. Stretches
with no Japanese, like an English definition, are kept as written. This module has no
Anki imports, so it can be tested on its own.
"""

import re
from pathlib import Path

from . import accents
from .kana import JAPANESE, has_kanji, to_hiragana
from .pitch import pitch_code
from .words import CONTENT, FIXED_WORDS, INFLECTING, SplitInsideToken, Word, snap_breaks, words

__all__ = ["annotate", "has_annotations", "strip", "load_fixes"]

# Field contents that are never touched: tags, sound tags, entities, existing brackets.
_PROTECTED = re.compile(r"<[^>]*>|\[[^\]]*\]|&#?[0-9a-zA-Z]+;")
# Tags that sit inside a sentence; any other tag (<br>, <div>, <img>) separates text.
_INLINE_TAG = re.compile(r"</?(?:b|i|u|s|em|strong|span|font|mark|small|big|sub|sup|a)(?:\s[^>]*)?/?>", re.I)
_SPACE_ENTITIES = {"&nbsp;", "&ensp;", "&emsp;", "&thinsp;", "&#160;", "&#8194;", "&#8195;", "&#12288;"}
# Whitespace of any kind, and list markers: ① ⑴ ⒈ ⒜ Ⓐ ⓐ ❶ ➀ ➊.
_SEPARATOR = re.compile(r"\s+|[\u2460-\u24ff\u2776-\u2793]")
_PLAIN_SPACE = re.compile(r"[ \t\r\n]")
# Japanese text and its punctuation, for deciding whether a space sits between Latin words.
_CJK = re.compile(r"[぀-ヿ㐀-䶿一-鿿豈-﫿々〆ー　-〿＀-￯]")
_KANA_ONLY = re.compile(r"^[぀-ヿー]+$")
# A reading annotation: kana, an optional comma part, an optional pitch. Not [sound:...].
_ANNOTATION = re.compile(r"\[(?!sound:)[぀-ヿー]*(?:,[぀-ヿー]*)?(?:;[hanok0-9,]*)?\]")

# Reading fixes: word -> (reading, pitch code or ""). Later files win over earlier ones.
_fixes: dict[str, tuple[str, str]] = {}


def load_fixes(path: Path) -> None:
    """Add reading fixes, one "word<TAB>reading<TAB>optional pitch" per line:

        私	わたし
        物	もの	h

    A fix applies wherever the word stands on its own. With no pitch code given,
    the pitch is looked up for the fixed reading.
    """
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        parts = [p.strip() for p in line.split("\t")]
        if line.startswith("#") or len(parts) < 2 or not parts[0] or not parts[1]:
            continue
        _fixes[parts[0]] = (to_hiragana(parts[1]), parts[2] if len(parts) > 2 else "")
        FIXED_WORDS[parts[0]] = to_hiragana(parts[1])


load_fixes(Path(__file__).with_name("data") / "readings.tsv")


def has_annotations(field: str) -> bool:
    """Whether the field already holds readings or pitch codes."""
    return any(m.group(0) not in ("[]",) for m in _ANNOTATION.finditer(field))


def strip(field: str) -> str:
    """Remove readings and pitch codes, and the spaces that were added between words."""
    text = _ANNOTATION.sub("", field)
    # Spaces next to Japanese were only separators; spaces between Latin words were &ensp;.
    text = re.sub(r" +(?=[　-ヿ㐀-鿿＀-￯]|<|$)", "", text)
    text = re.sub(r"(?<=[　-ヿ㐀-鿿＀-￯>]) +", "", text)
    text = re.sub(r"^ +", "", text)
    return text.replace("&ensp;", " ")


_DIGITS = str.maketrans("０１２３４５６７８９", "0123456789")
_NUMERALS = "一二三四五六七八九十"


def _is_base(ch: str) -> bool:
    """Characters the reading sits over: kanji, and digits."""
    return has_kanji(ch) or ch.translate(_DIGITS).isdigit()


def _accent(word: Word, surface: str, reading: str) -> int | None:
    """Kanjium's accent when it has the word, otherwise UniDic's."""
    head = word.head
    found = accents.lookup(surface, reading, head.pos1) if reading else None  # 一つ, 映画, お願い
    if found is None and reading and len(word.tokens) == 1 and head.pos1 not in INFLECTING:
        found = accents.lookup(head.lemma, reading, head.pos1)  # みんな under 皆, as みんな not みな
    # The lemma's own reading only for verbs and adjectives, whose endings change the reading.
    # Elsewhere a different reading is a different word: あんた is not 貴方 read あなた.
    if found is None and head.lemma_reading and (head.pos1 in INFLECTING or head.lemma_reading == reading):
        found = accents.lookup(head.lemma, head.lemma_reading, head.pos1)  # 陥る, 為る, 事
    return found if found is not None else head.accent


def _as_numerals(surface: str) -> str | None:
    """１つ -> 一つ, ２人 -> 二人: small numbers written in digits, so they can be read."""
    m = re.match(r"^([0-9０-９]+)(.*)$", surface)
    if not m:
        return None
    n = int(m.group(1).translate(_DIGITS))
    return _NUMERALS[n - 1] + m.group(2) if 1 <= n <= 10 else None


def _reading_and_code(word: Word) -> tuple[str, str]:
    surface, head = word.surface, word.head
    lookup_as, reading = surface, word.reading
    fixed_code = ""
    if surface in _fixes:
        reading, fixed_code = _fixes[surface]
        if not fixed_code and len(word.tokens) > 1:
            # Joined from pieces (遠+坂): only the dictionary's own entry, never a piece's pitch.
            return reading, pitch_code(accents.lookup(surface, reading), reading, "名詞")
    elif not reading and (numerals := _as_numerals(surface)):
        lookup_as = numerals
        reading = "".join(w.reading for w in words(numerals))
    elif reading and has_kanji(surface) and accents.known(surface) and accents.lookup(surface, reading) is None:
        # Not a real reading of this word (一本 as いちぽん): use the dictionary's, if it has just one.
        listed = accents.readings(surface)
        if len(listed) == 1:
            reading = listed[0]
    if fixed_code or head.pos1 not in CONTENT:
        return reading, fixed_code
    return reading, pitch_code(_accent(word, lookup_as, reading), reading or head.reading, head.pos1)


def _dictionary_form(word: Word, code: str) -> str:
    """",おいかける" for a verb or adjective with a drop: the pop-up draws its graph from it."""
    head = word.head
    if code.startswith("k") and head.pos1 in INFLECTING and head.base_reading:
        return "," + head.base_reading
    return ""


def _render(word: Word) -> str:
    surface = word.surface
    if not JAPANESE.search(surface):
        return surface
    reading, code = _reading_and_code(word)
    dictionary = _dictionary_form(word, code)
    if not any(_is_base(ch) for ch in surface):
        if _KANA_ONLY.match(surface) and code:
            return f"{surface}[{dictionary};{code}]"
        return surface
    if not reading:
        return surface
    # Kana at the end of the word stay outside the brackets: 陥る -> 陥[おちい]る.
    last = max(i for i, ch in enumerate(surface) if _is_base(ch))
    base, tail = surface[: last + 1], surface[last + 1 :]
    tail_reading = to_hiragana(tail)
    if tail and reading.endswith(tail_reading) and len(reading) > len(tail_reading):
        reading = reading[: -len(tail_reading)]
    else:
        base, tail = surface, ""
    inside = f"{reading}{dictionary};{code}" if code else reading
    return f"{base}[{inside}]{tail}"


# Parsing a field
##########################################################################
# A field becomes a list of (kind, text): "text" and "tag" (an inline tag) make up runs
# that are read as one; "block" (other tags, sound tags, entities), "space" and "marker"
# sit between runs.


def _elements(field: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []

    def text(chunk: str) -> None:
        pos = 0
        for m in _SEPARATOR.finditer(chunk):
            if m.start() > pos:
                out.append(("text", chunk[pos : m.start()]))
            out.append(("space" if m.group(0)[0].isspace() else "marker", m.group(0)))
            pos = m.end()
        if pos < len(chunk):
            out.append(("text", chunk[pos:]))

    pos = 0
    for m in _PROTECTED.finditer(field):
        text(field[pos : m.start()])
        piece = m.group(0)
        if piece in _SPACE_ENTITIES:
            out.append(("block", piece))
        elif _INLINE_TAG.fullmatch(piece):
            out.append(("tag", piece))
        else:
            out.append(("block", piece))
        pos = m.end()
    text(field[pos:])
    return out


def _join_words(ws: list[Word], tags: list[tuple[int, str]]) -> str:
    """Words separated by spaces, with each tag put back where it sat; a tag is boundary enough."""
    out, i, spaced = "", 0, False
    for w in ws:
        while i < len(tags) and tags[i][0] <= w.start:
            out += tags[i][1]
            i += 1
            spaced = False
        out += (" " if spaced else "") + _render(w)
        spaced = True
    return out + "".join(tag for _, tag in tags[i:])


def _annotate_run(run: list[tuple[str, str]]) -> str:
    """One run of text and inline tags, read as a single sentence."""
    plain, tags = "", []
    for kind, piece in run:
        if kind == "tag":
            tags.append((len(plain), piece))
        else:
            plain += piece
    if not JAPANESE.search(plain):
        return "".join(piece for _, piece in run)  # English, numbers, punctuation: as written
    # A tag in the middle of a word moves to the word's edge: 漠<b>然</b> -> <b>漠然</b>.
    snapped = snap_breaks(plain, [(o, tag.startswith("</")) for o, tag in tags])
    tags = sorted(((o, tag) for o, (_, tag) in zip(snapped, tags)), key=lambda t: t[0])
    try:
        return _join_words(words(plain, frozenset(o for o, _ in tags)), tags)
    except SplitInsideToken:
        # A tag inside a word (漠<b>然</b>): read the pieces on either side separately.
        return "".join(piece if kind == "tag" else _join_words(words(piece), []) for kind, piece in run)


def _plain(run: list[tuple[str, str]]) -> str:
    return "".join(piece for kind, piece in run if kind != "tag")


def annotate(field: str) -> str:
    """Annotate a whole field. Fields that already hold annotations come back unchanged."""
    if has_annotations(field) or not JAPANESE.search(field):
        return field
    els = _elements(field)
    out = ""
    last = ""  # what was written last: "word", "space" or "" after a tag, a block or the start
    prev_char = ""  # the last character of text written since the last block
    i = 0
    while i < len(els):
        kind, piece = els[i]
        if kind in ("text", "tag", "marker"):
            if kind == "marker":
                run, j = [("text", piece)], i + 1
            else:
                j = i
                while j < len(els) and els[j][0] in ("text", "tag"):
                    j += 1
                run = els[i:j]
            plain = _plain(run)
            if last == "word" and plain and not (run[0][0] == "tag"):
                out += " "
            out += piece if kind == "marker" else _annotate_run(run)
            if plain:
                prev_char = plain[-1]
            last = "word" if run[-1][0] != "tag" else ""
            i = j
        elif kind == "block":
            out += piece
            prev_char, last = "", ""
            i += 1
        else:  # whitespace
            special = _PLAIN_SPACE.sub("", piece)  # full-width and en spaces show on the card
            next_char = ""
            for k, p in els[i + 1 :]:
                if k == "block":
                    break
                if k in ("text", "marker"):
                    next_char = p[0]
                    break
            if special:
                # Padded only next to Japanese, where the template would read it as part of a word.
                left = " " if last == "word" and _CJK.match(prev_char or "x") else ""
                right = " " if next_char and _CJK.match(next_char) else ""
                out += left + special + right
            elif prev_char and next_char:
                # The templates drop plain spaces, so a space between two Latin words is kept as &ensp;.
                out += "&ensp;" if not (_CJK.match(prev_char) or _CJK.match(next_char)) else " "
            last = "space" if (special or (prev_char and next_char)) else last
            i += 1
    return out
