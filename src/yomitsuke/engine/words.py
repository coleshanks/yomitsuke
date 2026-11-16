"""Split Japanese text into the words that get a reading.

MeCab with UniDic splits text finely: 使って is 使っ + て, and 決められた is 決め + られ + た.
In the bracket format a verb or adjective keeps its endings, so tokens are grouped into
words here, the way bracket-annotated cards are usually split (tools/score.py measures it).
"""

import re
from dataclasses import dataclass, field
from functools import lru_cache

from . import accents
from .kana import KANJI, to_hiragana
from .pitch import first_accent

# Parts of speech that start a word of their own and can carry a pitch code.
CONTENT = {"名詞", "代名詞", "動詞", "形容詞", "形状詞", "副詞", "連体詞", "感動詞", "接続詞", "接頭辞"}
INFLECTING = {"動詞", "形容詞"}


@dataclass
class Token:
    surface: str
    reading: str  # hiragana, as written in this sentence; "" when unknown
    pos1: str
    pos2: str
    accent: int | None  # UniDic's
    lemma: str = ""  # dictionary form, as UniDic writes it (為る for する)
    lemma_reading: str = ""  # its reading, hiragana
    base_reading: str = ""  # the dictionary form's reading as written here: いい for いい, not よい
    start: int = 0  # where the token starts in the text


@dataclass
class Word:
    tokens: list[Token] = field(default_factory=list)
    compound_reading: str = ""  # set when tokens were joined into one dictionary word

    @property
    def surface(self) -> str:
        return "".join(t.surface for t in self.tokens)

    @property
    def start(self) -> int:
        return self.tokens[0].start

    @property
    def reading(self) -> str:
        """The whole word's reading, or "" if any part has none."""
        if self.compound_reading:
            return self.compound_reading
        parts = [t.reading for t in self.tokens]
        return "".join(parts) if all(parts) else ""

    @property
    def head(self) -> Token:
        """The token the word is named after: the noun after a prefix, otherwise the first."""
        first = self.tokens[0]
        if first.pos1 == "接頭辞" and len(self.tokens) > 1:
            return self.tokens[1]
        return first


@lru_cache(maxsize=1)
def _tagger():
    import fugashi  # imported late so the rest of the engine loads without it

    return fugashi.Tagger()


def _field(feature, name: str) -> str:
    value = getattr(feature, name, None)
    return "" if value in (None, "*") else value


class SplitInsideToken(ValueError):
    """A word boundary the caller asked for falls in the middle of a token."""


# 何 is なに before these particles (何が, 何を, 何も, 何か), whatever UniDic guesses.
_NANI_BEFORE = {"が", "を", "も", "か", "から", "より"}


def tokenize(text: str) -> list[Token]:
    tokens = []
    cursor = 0
    for node in _tagger()(text):
        f = node.feature
        kana = _field(f, "kana")
        found = text.find(node.surface, cursor)
        start = found if found >= 0 else cursor
        cursor = start + len(node.surface)
        tokens.append(
            Token(
                surface=node.surface,
                reading=to_hiragana(kana) if kana else "",
                pos1=_field(f, "pos1"),
                pos2=_field(f, "pos2"),
                accent=first_accent(_field(f, "aType")),
                lemma=_field(f, "lemma"),
                lemma_reading=to_hiragana(_field(f, "lForm")),
                base_reading=to_hiragana(_field(f, "kanaBase")),
                start=start,
            )
        )
    for tok, nxt in zip(tokens, tokens[1:]):
        if tok.surface == "何" and nxt.pos1 == "助詞" and nxt.surface in _NANI_BEFORE:
            tok.reading = tok.lemma_reading = "なに"
    return tokens


def _joins(word: Word, tok: Token) -> bool:
    """Whether tok belongs to the word before it."""
    last = word.tokens[-1]
    head = word.head
    # Endings on a verb or adjective: 使っ+て, 決め+られ+た, 離れ+たり, 使っ+て+も.
    if head.pos1 in INFLECTING:
        if tok.pos1 == "助動詞":
            return True
        if tok.pos1 == "助詞" and tok.pos2 == "接続助詞" and tok.surface in ("て", "で", "ば"):
            return True
        if tok.pos1 == "助詞" and tok.surface in ("たり", "だり"):
            return True
        if tok.pos1 == "助詞" and tok.surface == "も" and last.surface in ("て", "で"):
            return True
        if head.pos1 == "形容詞" and tok.pos1 == "接尾辞":  # 久し+ぶり, 高+さ
            return True
    # A prefix and what follows: お+金, ご+飯, お+願い, お+知らせ.
    if last.pos1 == "接頭辞" and tok.pos1 in ("名詞", "代名詞", "動詞"):
        return True
    # 個人+的, and numbers with their counter: 一+つ, ２+人.
    if last.pos1 == "名詞" and tok.pos1 == "接尾辞":
        if tok.pos2 == "形状詞的":
            return True
        if last.pos2 == "数詞":
            return True
    return False


# Pieces UniDic splits finely that a dictionary may list as one word: 正+社員, 文化+祭.
_COMPOUND_POS = {"名詞", "接頭辞", "接尾辞"}
_KATAKANA = re.compile(r"[ァ-ヺー]")
_LONGEST_COMPOUND = 4

# Words from the reading fix files (word -> reading). Pieces that spell one are joined
# whatever their part of speech, so a fix for a name like 遠坂 applies even though
# MeCab splits it into 遠 + 坂.
FIXED_WORDS: dict[str, str] = {}


def _compound_part(word: Word) -> bool:
    return all(t.pos1 in _COMPOUND_POS for t in word.tokens) and bool(
        KANJI.search(word.surface) or _KATAKANA.search(word.surface)
    )


def _join_compounds(ws: list[Word], breaks: frozenset[int]) -> list[Word]:
    """Join neighbouring nouns into one word when Kanjium lists the joined word, taking its reading."""
    out: list[Word] = []
    i = 0
    while i < len(ws):
        for j in range(min(len(ws), i + _LONGEST_COMPOUND), i + 1, -1):
            group = ws[i:j]
            if any(w.start in breaks for w in group[1:]):
                continue
            surface = "".join(w.surface for w in group)
            if surface in FIXED_WORDS:
                reading = FIXED_WORDS[surface]
            elif all(_compound_part(w) for w in group):
                reading = accents.compound_reading(surface, "".join(w.reading for w in group))
            else:
                continue
            if reading:
                out.append(Word([t for w in group for t in w.tokens], compound_reading=reading))
                i = j
                break
        else:
            out.append(ws[i])
            i += 1
    return out


def snap_breaks(text: str, offsets: list[tuple[int, bool]]) -> list[int]:
    """Move each tag offset that falls inside a token to the token's edge: an opening tag
    to its start, a closing tag to its end, so 漠<b>然</b> becomes <b>漠然</b>.
    offsets are (offset, is_closing_tag)."""
    spans = [(t.start, t.start + len(t.surface)) for t in tokenize(text)]
    out = []
    for offset, closing in offsets:
        for start, end in spans:
            if start < offset < end:
                offset = end if closing else start
                break
        out.append(offset)
    return out


def words(text: str, breaks: frozenset[int] = frozenset()) -> list[Word]:
    """The words in text. breaks are offsets where a word must end (where a tag such as <b> sits)."""
    tokens = tokenize(text)
    for tok in tokens:
        if any(tok.start < b < tok.start + len(tok.surface) for b in breaks):
            raise SplitInsideToken(tok.surface)
    out: list[Word] = []
    for tok in tokens:
        if out and tok.start not in breaks and _joins(out[-1], tok):
            out[-1].tokens.append(tok)
        else:
            out.append(Word([tok]))
    return _join_compounds(out, breaks)
