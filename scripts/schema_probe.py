"""Does a tool parameter's description reach the SERVED JSON Schema? (py3.10 regression)

WHY A SCRIPT. The 1.0.8 release failed CI on py3.10 only: `test_every_tool_parameter_is_described`
reported `dossier`'s `kind`, `qualified` and `target` as undescribed, and those are exactly the
parameters whose default is `None`. Python 3.10's `get_type_hints` wraps such an annotation in
`Optional[...]`, which HIDES `__metadata__` from the outer type; 3.11 dropped that implicit
wrapping. So the test's introspection is version-dependent.

That makes the ANNOTATION SHAPE the wrong thing to assert. What matters is the served JSON
Schema — the one channel a client cannot truncate. This prints it, so the question "is the
description actually lost on 3.10" is answered by the artifact rather than by reasoning about
typing internals.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))


##
# @brief Print each tool parameter's description as the served schema carries it.
# @return 0 when every parameter is described, 1 when any is bare.
# @version 1
def main() -> int:
    """@brief Report described/bare parameters from the generated schema.
    @return Exit status.
    @version 1
    """
    from pydantic import TypeAdapter  # noqa: PLC0415
    import typing  # noqa: PLC0415

    from clew.mcp_server.server import DocsDbServer  # noqa: PLC0415
    from clew.mcp_server.tools_query import QueryTools  # noqa: PLC0415

    print(f"python {sys.version.split()[0]}")
    bad = 0
    for owner, name in (
        (QueryTools, "dossier"),
        (QueryTools, "search"),
        (DocsDbServer, "index"),
        (DocsDbServer, "propose_declaration"),
    ):
        fn = getattr(owner, name)
        hints = typing.get_type_hints(fn, include_extras=True)
        print(f"\n=== {name} ===")
        for pname, hint in hints.items():
            if pname in ("return", "self", "ctx"):
                continue
            ## The SERVED artifact, not the annotation shape: pydantic resolves Annotated
            ## metadata itself and does not apply 3.10's implicit-Optional wrapping.
            try:
                schema = TypeAdapter(hint).json_schema()
            except Exception as exc:  # noqa: BLE001
                print(f"  {pname:<12} SCHEMA ERROR {exc}")
                bad += 1
                continue
            desc = schema.get("description") or ""
            ## An Optional[Annotated[...]] renders as anyOf; the description may sit in a branch.
            if not desc:
                for branch in schema.get("anyOf", ()):
                    if isinstance(branch, dict) and branch.get("description"):
                        desc = branch["description"]
                        break
            outer_meta = bool(getattr(hint, "__metadata__", ()))
            state = "DESCRIBED" if desc else "BARE"
            if not desc:
                bad += 1
            print(f"  {pname:<12} {state:<10} outer __metadata__={outer_meta!s:<5} {desc[:60]}")
            if not desc:
                print(f"      full schema: {json.dumps(schema)[:200]}")
    print(f"\n{'FAIL' if bad else 'OK'}: {bad} bare parameter(s)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
