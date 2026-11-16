"""The card display menu reads a note type's setup from its templates and only changes its own markers."""

from yomitsuke import templates
from yomitsuke.templates import BEGIN, END, apply, read, remove, snippet, update_display


def notetype(front: str, back: str, fields=("Word", "Sentence", "Audio", "Picture"), name="Card 1") -> dict:
    return {
        "flds": [{"name": f} for f in fields],
        "tmpls": [{"name": name, "qfmt": front, "afmt": back}],
        "css": ".card { font-size: 30px; }",
    }


def side(nt: dict, key: str = "qfmt") -> str:
    return nt["tmpls"][0][key]


def without_display(html: str) -> str:
    return html.split(BEGIN)[0].rstrip()


# An ordinary note type nobody has set up.
PLAIN_FRONT = '<div class="word">{{Word}}</div>\n<hr>\n{{Sentence}}'
PLAIN_BACK = '{{FrontSide}}\n<hr id=answer>\n{{Audio}}\n<img src="{{Picture}}">\n{{Sentence}}'

# Set up by hand with <div> wrappers, the display at the end of both sides.
SET_UP_FRONT = '<div class="ym" data-mode="plain">{{Word}}</div>\n<hr>\n' \
    '<div style=\'font-size: 38px;\'><div class="ym" data-mode="plain">{{Sentence}}</div></div>\n\n' + snippet() + "\n"
SET_UP_BACK = '<div class="ym" data-mode="colored">{{Word}}</div>{{Audio}}\n<hr>\n' \
    '<!-- <div>{{Sentence}}</div> -->\n<div class="ym" data-mode="reading">{{Sentence}}</div>\n{{Picture}}\n\n' + snippet() + "\n"


def test_an_ordinary_note_type_reads_as_not_set_up():
    setup = read(notetype(PLAIN_FRONT, PLAIN_BACK))
    assert setup.fields == ["Word", "Sentence", "Audio"]  # Picture is only inside an attribute
    assert setup.sides == {"Word": {"front"}, "Sentence": {"front", "back"}, "Audio": {"back"}}
    assert setup.modes == {}
    assert setup.japanese() == []
    assert setup.display == "none"


def test_a_set_up_note_type_reads_back_its_setup():
    setup = read(notetype(SET_UP_FRONT, SET_UP_BACK))
    assert setup.modes == {
        "Word": {"front": "plain", "back": "colored"},
        "Sentence": {"front": "plain", "back": "reading"},
    }
    assert setup.japanese() == ["Word", "Sentence"]
    assert setup.display == "current"


def test_an_older_display_is_noticed():
    old = SET_UP_FRONT.replace("use strict", "use strict ")
    assert read(notetype(old, SET_UP_BACK)).display == "old"


def test_adding_wraps_fields_inline_and_leaves_everything_else():
    nt = notetype(PLAIN_FRONT, PLAIN_BACK)
    new = apply(nt, {"Sentence": {"front": "plain", "back": "reading"}})
    assert without_display(side(new)) == (
        '<div class="word">{{Word}}</div>\n<hr>\n<span class="ym" data-mode="plain">{{Sentence}}</span>'
    )
    assert without_display(side(new, "afmt")) == (
        '{{FrontSide}}\n<hr id=answer>\n{{Audio}}\n<img src="{{Picture}}">\n'
        '<span class="ym" data-mode="reading">{{Sentence}}</span>'
    )
    assert side(new) == '<div class="word">{{Word}}</div>\n<hr>\n<span class="ym" data-mode="plain">{{Sentence}}</span>\n' + snippet() + "\n"
    assert new["css"] == nt["css"]
    assert nt["tmpls"][0]["qfmt"] == PLAIN_FRONT  # the original isn't changed


def test_applying_the_same_setup_changes_nothing():
    nt = notetype(SET_UP_FRONT, SET_UP_BACK)
    assert apply(nt, read(nt).modes) == nt
    once = apply(notetype(PLAIN_FRONT, PLAIN_BACK), {"Word": {"front": "plain"}})
    assert apply(once, read(once).modes) == once


def test_an_existing_div_wrapper_keeps_its_tag():
    nt = notetype(SET_UP_FRONT, SET_UP_BACK)
    new = apply(nt, {"Word": {"front": "plain", "back": "reading"}, "Sentence": {"front": "plain", "back": "reading"}})
    assert '<div class="ym" data-mode="reading">{{Word}}</div>{{Audio}}' in side(new, "afmt")


def test_dropping_a_field_unwraps_it():
    nt = notetype(SET_UP_FRONT, SET_UP_BACK)
    new = apply(nt, {"Word": {"front": "plain", "back": "colored"}})
    assert "<div style='font-size: 38px;'>{{Sentence}}</div>" in side(new)
    assert '\n{{Sentence}}\n{{Picture}}' in side(new, "afmt")
    assert '<!-- <div>{{Sentence}}</div> -->' in side(new, "afmt")  # the comment is left alone
    assert snippet() in side(new)


def test_remove_takes_everything_out():
    nt = apply(notetype(PLAIN_FRONT, PLAIN_BACK), {"Word": {"front": "plain"}, "Sentence": {"front": "plain", "back": "reading"}})
    assert remove(nt) == notetype(PLAIN_FRONT, PLAIN_BACK)


def test_add_then_remove_is_exact_whatever_the_template_ends_with():
    for ending in ("", "\n", "\n\n", "  \n"):
        nt = notetype(PLAIN_FRONT + ending, PLAIN_BACK + ending)
        assert remove(apply(nt, {"Sentence": {"front": "plain", "back": "reading"}})) == nt


def test_remove_on_a_set_up_note_type():
    new = remove(notetype(SET_UP_FRONT, SET_UP_BACK))
    assert 'class="ym"' not in side(new) + side(new, "afmt")
    assert BEGIN not in side(new) + side(new, "afmt")
    assert side(new).endswith("<div style='font-size: 38px;'>{{Sentence}}</div>\n")


def test_fields_through_ankis_filters_are_left_alone():
    nt = notetype("{{furigana:Sentence}}\n{{#Word}}{{Word}}{{/Word}}", "{{FrontSide}}")
    setup = read(nt)
    assert setup.fields == ["Word"]
    assert setup.filtered == {"Sentence": "furigana"}
    new = apply(nt, {"Sentence": {"front": "reading"}, "Word": {"front": "plain"}})
    assert without_display(side(new)) == (
        '{{furigana:Sentence}}\n{{#Word}}<span class="ym" data-mode="plain">{{Word}}</span>{{/Word}}'
    )


def test_fields_in_scripts_styles_and_comments_are_left_alone():
    front = '<script>var w = "{{Word}}";</script><style>/* {{Word}} */</style><!-- {{Word}} -->{{Word}}'
    new = apply(notetype(front, ""), {"Word": {"front": "plain"}})
    assert without_display(side(new)) == (
        '<script>var w = "{{Word}}";</script><style>/* {{Word}} */</style><!-- {{Word}} -->'
        '<span class="ym" data-mode="plain">{{Word}}</span>'
    )


def test_update_display_only_swaps_the_script():
    old_block = snippet().replace("use strict", "use strict ")
    nt = notetype(SET_UP_FRONT.replace(snippet(), old_block), SET_UP_BACK.replace(snippet(), old_block))
    new = update_display(nt)
    assert new == notetype(SET_UP_FRONT, SET_UP_BACK)
    assert update_display(notetype(PLAIN_FRONT, PLAIN_BACK)) == notetype(PLAIN_FRONT, PLAIN_BACK)


def test_every_card_type_of_a_note_type_is_changed():
    nt = notetype("{{Word}}", "{{FrontSide}}<hr>{{Sentence}}")
    nt["tmpls"].append({"name": "Reverse", "qfmt": "{{Sentence}}", "afmt": "{{Word}}"})
    new = apply(nt, {"Word": {"front": "plain", "back": "colored"}, "Sentence": {"front": "plain", "back": "reading"}})
    assert without_display(new["tmpls"][1]["qfmt"]) == '<span class="ym" data-mode="plain">{{Sentence}}</span>'
    assert without_display(new["tmpls"][1]["afmt"]) == '<span class="ym" data-mode="colored">{{Word}}</span>'


def test_changes_lists_what_moves():
    nt = notetype(PLAIN_FRONT, PLAIN_BACK)
    text = templates.changes(nt, apply(nt, {"Sentence": {"front": "plain"}}))
    assert "Card 1, front:" in text
    assert '+<span class="ym" data-mode="plain">{{Sentence}}</span>' in text
    assert "+<!-- yomitsuke display (script) -->" in text
    assert templates.changes(nt, nt) == ""


def test_the_display_never_contains_what_anki_rewrites():
    block = snippet()
    assert block.startswith(BEGIN) and block.endswith(END)
    assert "{{" not in block and "[sound:" not in block


def test_a_display_under_a_past_name_is_recognised_and_replaced(monkeypatch):
    old = snippet().replace(f"{templates.NAME} display", "oldname display")
    monkeypatch.setattr(templates, "_BLOCK", templates._block_pattern((templates.NAME, "oldname")))
    nt = notetype(SET_UP_FRONT.replace(snippet(), old), SET_UP_BACK.replace(snippet(), old))
    assert read(nt).display == "old"
    assert update_display(nt) == notetype(SET_UP_FRONT, SET_UP_BACK)
