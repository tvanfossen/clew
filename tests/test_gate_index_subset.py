# SPDX-License-Identifier: MIT
"""What the gate checks is a subset of what the index holds, by the owner's ruling.

THE INVARIANT USED TO BE EQUALITY: one TypeScript rule for "what is a function", shared by the
index and the doc gate (`clew/guard/ts_parser.py`), so the two could never disagree. The 1.3.0
TypeScript audit widened the INDEX — interface signatures, object-literal functions, named
closures, typed members — and the owner ruled that the GATE stays at module- and class-level
definitions: it must not demand documentation for a closure or a type signature. So the invariant
is now a subset, and this test states it.

AND ONE THING THE GATE GAINS: a mixin class's members. `const M = (s: T) => class extends s {...}`
holds a module's whole API on mattermost-mobile, and the gate stopped at the arrow exactly as the
index used to, so those methods could go undocumented with nothing saying so.

@brief Tests that the gate's TypeScript definitions are a subset of the index's.
@version 1
"""

from __future__ import annotations

import lang_parsing_substrate as lps

from clew.guard.ts_parser import parse_functions_ts
from clew.jsast import harvest_definitions

_SRC = """\
type Constructor<T> = new (...args: any[]) => T;

/** Base. */
export class ClientBase { doFetch(url: string) { return url; } }

/** A mixin. */
const ClientFiles = <TBase extends Constructor<ClientBase>>(superclass: TBase) => class extends superclass {
    /** Gets a URL. */
    getFileUrl(id: string) { return this.doFetch(id); }
    upload = async (f: string) => { return this.doFetch(f); };
};

export interface Svc { run(): void; }

export const transitions = { action: (s: string) => s };

export function outer() {
    const inner = () => 1;
    return inner();
}
"""


## @brief The gate checks a mixin's members, and nothing the index does not hold.
## @return None.
## @version 1
def test_the_gate_checks_mixin_members_and_stays_within_the_index() -> None:
    """THREE CLAIMS: the gate now sees `getFileUrl` and `upload`; it does NOT see the closure
    `inner`, the signature `run`, or the object function `action` (owner's ruling); and every name
    it sees is a definition the index holds.

    @brief Gate ⊆ index, and the gate covers mixin members.
    @return None.
    @version 1
    """
    gate = {f.name for f in parse_functions_ts(_SRC, "typescript")}
    index = {
        f["name"]
        for f in harvest_definitions(lps.parse_tree("typescript", _SRC.encode()), _SRC.encode())[
            "functions"
        ]
    }
    assert {"getFileUrl", "upload"} <= gate, gate
    assert not {"inner", "run", "action"} & gate, gate
    assert gate <= index, f"the gate checks what the index does not hold: {sorted(gate - index)}"
