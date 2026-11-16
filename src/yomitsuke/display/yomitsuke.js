// yomitsuke display: shows word[reading;pitch] text as furigana with pitch accent colours.
//
// Put each field in an element with class "ym" and a mode. This file goes into card templates,
// where Anki reads double curly braces as fields and square-bracketed sound tags as audio, even
// in a comment, so neither may appear here (the add-on checks).
//   data-mode="plain"     no readings, no colour (a card's front)
//   data-mode="reading"   readings; colour and pitch graph on hover or tap
//   data-mode="colored"   readings and colour; pitch graph on hover or tap
//
// The format, one word at a time, words separated by spaces:
//   陥[おちい;k3]る   reading over the kanji, kana after it outside, pitch code k3
//   追[お,おいかける;k4]いかけたい   with the dictionary form, which the graph is drawn from
//   こと[;o]         a kana word with just a pitch code
// Pitch codes: h flat, a drop after the first mora, o drop after the last, n2 n3... drop after
// that mora, k1 k2... a verb or adjective with a drop. Several codes ("a,h") are all graphed.
//
// Anki may keep one page open and swap the card in, so everything here stays inside this
// function and each field is only processed once.
(() => {
  "use strict";

  const STYLE_ID = "ym-style";
  const STYLE = "/*CSS*/";

  // base[reading,dictionary;codes]tail. Only kana and pitch codes count, so a sound tag doesn't.
  const WORD = /([^\s\[\]]*?)\[([぀-ヿー]*)(?:,([぀-ヿー]*))?(?:;([hanok0-9,]*))?\]([^\s\[\]<]*)/g;
  const HAS_WORD = new RegExp(WORD.source);
  // Punctuation in front of a word (「, （) stays outside its furigana.
  const LEAD = /^[^\p{Script=Han}\p{Script=Hiragana}\p{Script=Katakana}0-9０-９ー々〆]*/u;
  const KANA_ONLY = /^[぀-ヿー]*$/;
  const SMALL_KANA = "ゃゅょぁぃぅぇぉゎャュョァィゥェォヮ";
  const TYPES = { h: "heiban", a: "atamadaka", o: "odaka", n: "nakadaka", k: "kifuku" };

  function addStyle() {
    if (document.getElementById(STYLE_ID)) return;
    const style = document.createElement("style");
    style.id = STYLE_ID;
    style.textContent = STYLE;
    document.head.appendChild(style);
  }

  // きょう -> ["きょ", "う"]: small kana belong to the mora before them.
  function morae(kana) {
    const out = [];
    for (const ch of kana) {
      if (SMALL_KANA.includes(ch) && out.length) out[out.length - 1] += ch;
      else out.push(ch);
    }
    return out;
  }

  // "k4" -> { type: "kifuku", drop: 4 }. drop is the mora the pitch falls after; 0 for none.
  function parseCode(code, moraCount) {
    const letter = code[0];
    const number = parseInt(code.slice(1), 10);
    const drop = { h: 0, a: 1, o: moraCount }[letter] ?? (Number.isNaN(number) ? 0 : number);
    return { type: TYPES[letter] || "", drop, label: code.toUpperCase() };
  }

  // The graph is centred under its word; near the screen's edge, slide it back on.
  function keepOnScreen(pop) {
    pop.style.translate = "";
    requestAnimationFrame(() => {
      const box = pop.getBoundingClientRect();
      const width = document.documentElement.clientWidth;
      const margin = 4;
      let shift = 0;
      if (box.left < margin) shift = margin - box.left;
      else if (box.right > width - margin) shift = width - margin - box.right;
      if (shift) pop.style.translate = `${shift}px 0`;
    });
  }

  function element(tag, className, text) {
    const el = document.createElement(tag);
    if (className) el.className = className;
    if (text) el.textContent = text;
    return el;
  }

  // One line of the pop-up: the kana with a line over the high morae and a tick at the drop.
  function graph(kana, code) {
    const parts = morae(kana);
    const { type, drop, label } = parseCode(code, parts.length);
    const row = element("span", `ym-row ym-${type}`);
    const line = element("span", "ym-graph");
    parts.forEach((mora, i) => {
      // Flat: low then high. Otherwise high from the second mora (the first if the drop is
      // after it) up to the drop, low after.
      const high = drop === 0 ? i > 0 || parts.length === 1 : drop === 1 ? i === 0 : i > 0 && i < drop;
      const cls = ["ym-mora", high ? "ym-high" : "ym-low"];
      if (drop > 0 && i === drop - 1) cls.push("ym-drop");
      line.appendChild(element("span", cls.join(" "), mora));
    });
    row.append(line, element("span", "ym-code", label));
    return row;
  }

  function word(match, mode) {
    const [, rawBase, reading, dictionary, codeText, tail] = match;
    const lead = rawBase.match(LEAD)[0];
    const base = rawBase.slice(lead.length);
    const codes = (codeText || "").split(",").filter(Boolean);
    const out = document.createDocumentFragment();
    if (lead) out.append(lead);

    if (mode === "plain") {
      out.append(base + tail);
      return out;
    }

    const el = element("span", "ym-word");
    if (codes.length) el.classList.add(`ym-${parseCode(codes[0], 0).type}`);
    if (reading && !KANA_ONLY.test(base)) {
      const ruby = element("ruby", "", base);
      ruby.appendChild(element("rt", "", reading));
      el.appendChild(ruby);
    } else {
      el.append(base);
    }
    if (tail) el.append(tail);

    if (codes.length) {
      // The dictionary form when the card has it (k codes are counted on it); otherwise the
      // word as read here, which is close enough for most words.
      const kanaTail = [...tail].filter((ch) => KANA_ONLY.test(ch)).join("");
      const kana = dictionary || (reading ? reading + kanaTail : KANA_ONLY.test(base + tail) ? base + tail : "");
      if (kana) {
        const pop = element("span", "ym-pop");
        codes.forEach((code) => pop.appendChild(graph(kana, code)));
        el.appendChild(pop);
        el.tabIndex = 0; // a tap focuses it on phones, which shows the graph
        el.addEventListener("pointerenter", () => keepOnScreen(pop));
        el.addEventListener("focus", () => keepOnScreen(pop));
      }
    }
    out.appendChild(el);
    return out;
  }

  function render(field) {
    const mode = field.dataset.mode || "reading";
    const texts = [];
    const walker = document.createTreeWalker(field, NodeFilter.SHOW_TEXT);
    while (walker.nextNode()) texts.push(walker.currentNode);
    // Only a field with readings has spaces that are just separators.
    if (!texts.some((t) => HAS_WORD.test(t.data))) return;

    for (const node of texts) {
      const text = node.data;
      const out = document.createDocumentFragment();
      let pos = 0;
      for (const match of text.matchAll(WORD)) {
        out.append(text.slice(pos, match.index).replaceAll(" ", ""));
        out.appendChild(word(match, mode));
        pos = match.index + match[0].length;
      }
      out.append(text.slice(pos).replaceAll(" ", ""));
      node.replaceWith(out);
    }
  }

  addStyle();
  for (const field of document.querySelectorAll(".ym:not([data-ym-done])")) {
    field.dataset.ymDone = "";
    render(field);
  }
})();
