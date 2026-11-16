"""yomitsuke: write furigana and pitch accent into Japanese cards, in bulk, from the browser.

Inside Anki this sets up the add-on. Outside Anki (tests, tools) importing the package
does nothing, so yomitsuke.engine can be used on its own.
"""

import sys
from pathlib import Path

_here = Path(__file__).resolve().parent
_vendor = _here / "vendor"
if _vendor.is_dir() and str(_vendor) not in sys.path:
    sys.path.insert(0, str(_vendor))  # the bundled fugashi and UniDic

try:
    from aqt import mw
except ImportError:
    mw = None

if mw is not None:
    try:
        import fugashi  # noqa: F401 (compiled, bundled for the Pythons Anki ships)
    except ImportError as err:
        # A newer Anki on a Python the build doesn't include yet: say so instead of a traceback.
        from aqt.utils import showWarning

        python = f"{sys.version_info.major}.{sys.version_info.minor}"
        message = (
            f"yomitsuke is turned off: this Anki runs Python {python}, and this build of yomitsuke "
            f"only includes its word splitter for Python 3.13 and 3.14. A new build will fix it.\n\n({err})"
        )
        mw.progress.single_shot(1000, lambda: showWarning(message, title="yomitsuke"), False)
    else:
        from . import addon

        addon.setup()
