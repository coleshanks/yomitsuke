"""The engine writes the format the existing card templates read, and touches nothing else."""

import pytest

from yomitsuke.engine import annotate, has_annotations, strip
from yomitsuke.engine.pitch import first_accent, pitch_code


@pytest.mark.parametrize(
    ("accent", "reading", "pos", "code"),
    [
        (0, "さくら", "名詞", "h"),
        (1, "いのち", "名詞", "a"),
        (3, "おとこ", "名詞", "o"),
        (1, "て", "名詞", "o"),  # one mora with a drop after it is odaka
        (2, "みずうみ", "名詞", "n2"),
        (1, "はいる", "動詞", "k1"),  # 入る, K1 in the pop-up
        (0, "あそぶ", "動詞", "h"),
        (2, "あかい", "形容詞", "k2"),
        (None, "が", "助詞", ""),
    ],
)
def test_pitch_codes(accent, reading, pos, code):
    assert pitch_code(accent, reading, pos) == code


def test_only_the_first_accent_is_used():
    assert first_accent("3,0") == 3
    assert first_accent("*") is None


def test_kana_after_the_kanji_stays_outside_the_brackets():
    assert annotate("陥る") == "陥[おちい,おちいる;k3]る"


def test_a_verb_keeps_its_endings():
    assert annotate("使って") == "使[つか;h]って"
    assert annotate("決められた") == "決[き;h]められた"


def test_kana_only_words_get_a_pitch_code_and_particles_stay_bare():
    out = annotate("ゲームをすること")
    assert "ゲーム[;a]" in out
    assert " を " in out
    assert "[;" in out.split("を")[1]  # する and こと are annotated too


def test_one_pitch_only_and_a_dictionary_form_only_for_drops():
    # The pop-up draws a k-code graph from the dictionary form, so k words carry it.
    assert annotate("遠のいた") == "遠[とお,とおのく;k3]のいた"
    assert annotate("追いかけたい") == "追[お,おいかける;k4]いかけたい"
    assert annotate("いい") == "いい[,いい;k1]"  # as written, not 良い's よい
    assert "," not in annotate("使って")  # heiban: drawn without it
    assert "," not in annotate("映画")


def test_words_are_separated_by_spaces():
    assert annotate("羊を放牧する").split(" ")[1] == "を"


def test_bold_sound_and_images_are_untouched():
    field = '彼は<b>放牧する</b>[sound:a b.mp3]<img src="x 1.jpg">'
    out = annotate(field)
    assert "<b>" in out and "</b>" in out
    assert "[sound:a b.mp3]" in out
    assert '<img src="x 1.jpg">' in out
    assert "放牧[ほうぼく;h]" in out


def test_english_is_left_alone():
    assert annotate("a plain English definition") == "a plain English definition"
    assert annotate("I like 本") == "I&ensp;like 本[ほん;a]"


def test_annotated_fields_are_skipped():
    field = "牧場[ぼくじょう;h] を 見[み;k1]る"
    assert has_annotations(field)
    assert annotate(field) == field
    assert not has_annotations("[sound:x.mp3] no readings here")


def test_strip_undoes_annotate():
    text = "<b>羊</b>を放牧する"
    assert strip(annotate(text)) == text


def test_reading_fixes_apply_and_keep_a_looked_up_pitch():
    assert annotate("私") == "私[わたし;h]"
    assert annotate("不気味") == "不気味[ぶきみ;h]"


def test_pitch_comes_from_kanjium_first():
    assert annotate("映画") == "映画[えいが;a]"  # Kanjium 1; UniDic says 0
    assert annotate("所") == "所[ところ;h]"  # Kanjium 0; UniDic says 3


def test_a_prefix_joins_the_word_after_it():
    assert annotate("お願い").startswith("お願[おねが;")


def test_small_numbers_in_digits_are_read():
    assert annotate("１つ") == "１[ひと;n2]つ"
    assert annotate("２人").startswith("２人[ふたり")


def test_a_reading_the_dictionary_doesnt_know_is_replaced_by_its_only_one():
    assert annotate("一本").startswith("一本[いっぽん")


def test_a_sentence_is_read_whole_across_inline_tags():
    # Read alone, である after </b> came out as で[;o] ある[;a].
    assert annotate("それが<b>家訓</b>である") == "それ[;h] が<b>家訓[かくん;h]</b>で ある[,ある;k1]"


def test_a_tag_inside_a_word_moves_to_its_edge():
    assert annotate("漠<b>然</b>と") == "<b>漠然[ばくぜん;h]</b>と"


def test_list_markers_and_odd_spaces_separate_words():
    assert "力[ちから;o]" in annotate("<div>①\u2002力を出して</div>")  # not ①力 as a number
    assert "船[ふね;a]" in annotate("❶\u2002船など")
    assert "\u2002" in annotate("❶\u2002船など")


def test_full_width_spaces_are_kept():
    assert "　" in annotate("乗り切れば　この私が")


def test_english_in_a_definition_is_kept_as_written():
    out = annotate("Ⓑ prohibition, ban (also written as 禁め)")
    assert "prohibition,&ensp;ban&ensp;(also&ensp;written&ensp;as" in out


def test_compounds_listed_in_the_dictionary_stay_one_word():
    assert annotate("正社員") == "正社員[せいしゃいん;n3]"
    assert annotate("文化祭") == "文化祭[ぶんかさい;n3]"
    assert annotate("ホームイン") == "ホームイン[;n3]"


def test_nani_before_ga_and_wo():
    assert annotate("何があっても").startswith("何[なに;a] が")
    assert annotate("何を").startswith("何[なに;a]")


def test_kana_words_find_their_kanji_entry():
    assert annotate("みんな") == "みんな[;o]"  # 皆 みんな 3 in Kanjium


def test_a_colloquial_reading_is_not_given_its_lemmas_pitch():
    assert annotate("あんた") == "あんた[;a]"  # 貴方 read あなた is n2; あんた is 1


def test_a_fix_joins_a_name_split_into_pieces(tmp_path):
    from yomitsuke.engine import load_fixes

    fixes = tmp_path / "my-readings.tsv"
    fixes.write_text("遠坂\tとおさか\n", encoding="utf-8")
    load_fixes(fixes)
    assert annotate("遠坂家の家訓").startswith("遠坂[とおさか] ")


def test_en_spaces_between_english_words_are_kept_bare():
    out = annotate("Ⓐ \u2002caution,\u2002warning<br>禁め")
    assert "caution,\u2002warning" in out
