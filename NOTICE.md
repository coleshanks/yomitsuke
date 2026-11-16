# Third-party notices

yomitsuke's own code is MIT (see [LICENSE](LICENSE)). The add-on bundles these, each under its own licence:

| What | Used for | Licence | In the add-on |
|---|---|---|---|
| [Kanjium](https://github.com/mifunetoshiro/kanjium) pitch accent list, by Uros O. | pitch accents | [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) | `engine/data/accents.tsv`, credited in `engine/data/README.md` |
| [fugashi](https://github.com/polm/fugashi) | splitting text into words | MIT | `vendor/fugashi-1.5.2.dist-info/licenses/LICENSE` |
| [MeCab](https://taku910.github.io/mecab/), inside fugashi | the word splitter itself | BSD (also GPL, LGPL) | `vendor/fugashi-1.5.2.dist-info/licenses/LICENSE.mecab` |
| [unidic-lite](https://github.com/polm/unidic-lite) | packaging the dictionary | MIT | `vendor/unidic_lite/LICENSE` |
| [UniDic](https://clrd.ninjal.ac.jp/unidic/) 2.1.2 | the dictionary: readings and accents | BSD (also GPL, LGPL) | `vendor/unidic_lite/dicdir/BSD` and `COPYING` |

The pitch accent notation was provided by Uros O. through his free database. Kanjium builds on EDICT by the Electronic Dictionary Research and Development Group, used in conformance with the Group's [licence](https://www.edrdg.org/edrdg/licence.html).
