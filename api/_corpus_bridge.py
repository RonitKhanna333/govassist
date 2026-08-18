"""Makes data/scripts importable from api/ without duplicating it.

data/scripts/ is flat, non-package modules (grammar.py, parse_scheme.py, ...)
by deliberate choice -- it's corpus CLI tooling, kept simple. api/ is a real
package because it's going to grow into a service. Rather than choose one
style for both, this bridges them: importing this module once puts
data/scripts on sys.path, so `import grammar` and `from parse_scheme import
repo_root` work the same way inside api/ as they already do in tests/.

Every api/ module that needs grammar.py or parse_scheme.py imports this
first:

    import api._corpus_bridge  # noqa: F401
    import grammar
"""

from __future__ import annotations

import sys
from pathlib import Path

_CORPUS_SCRIPTS = Path(__file__).resolve().parent.parent / "data" / "scripts"

if not _CORPUS_SCRIPTS.is_dir():  # pragma: no cover -- misconfigured checkout
    raise RuntimeError(f"expected data/scripts at {_CORPUS_SCRIPTS}, not found")

if str(_CORPUS_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_CORPUS_SCRIPTS))
