"""Write yomitsuke's card display to dist/yomitsuke-display.html, to read or paste by hand.

The display is src/yomitsuke/display/yomitsuke.js with yomitsuke.css inlined, as one <script>
block. In Anki, Tools > yomitsuke Card Display puts it into note types and keeps it up to date.

    uv run python tools/display.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from yomitsuke.templates import snippet  # noqa: E402


def main() -> None:
    out = ROOT / "dist" / "yomitsuke-display.html"
    out.parent.mkdir(exist_ok=True)
    out.write_text(snippet(), encoding="utf-8")
    print(f"{out.relative_to(ROOT)}: {out.stat().st_size / 1024:.1f} KB")


if __name__ == "__main__":
    main()
