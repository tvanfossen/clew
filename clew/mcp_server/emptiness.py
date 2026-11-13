# SPDX-License-Identifier: MIT
"""Compatibility alias: the emptiness grading moved to `clew.query.emptiness` in 1.3.1.

MOVED, NOT COPIED. The export API (`clew.query.export`) grades an empty search exactly as the MCP
tool does, and the query package must not import the MCP package, so the module now lives under
`clew.query`. This name stays importable because tests and any out-of-tree caller read it; it is
the SAME module object, so a monkeypatch through either name patches both.

@brief Alias of clew.query.emptiness.
@version 2
"""

from __future__ import annotations

import sys

from ..query import emptiness as _emptiness

sys.modules[__name__] = _emptiness
