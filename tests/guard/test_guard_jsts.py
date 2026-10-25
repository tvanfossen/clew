"""JavaScript / TypeScript (JSDoc) support in the absorbed gate.

Opt-in like Rust: a repo declares `validate.languages.javascript` / `typescript`. The block
is a `/** */` JSDoc comment above the function, or above the `export` / `const` around it;
its summary stands in for @brief; @return is required only on request, and then only where
a TypeScript annotation says the function returns a value.
"""

from __future__ import annotations

from textwrap import dedent

import pytest

from clew.guard.config import CONFIG_DEFAULTS, apply_opt_in_languages, deep_merge
from clew.guard.main import validate_file
from clew.guard.parser import parse_functions
from clew.guard.ts_languages import language_for_file


def _config(**languages) -> dict:
    user = {"validate": {"languages": languages or {"javascript": {}, "typescript": {}}}}
    return apply_opt_in_languages(deep_merge(CONFIG_DEFAULTS, user), user)


def _parse(lang: str, src: str):
    return {f.name: f for f in parse_functions(dedent(src), [], None, lang_name=lang)}


TS = """\
    /**
     * Adds one.
     * @version 2
     * @req REQ-X-001
     */
    export function add(x: number): number { return x + 1; }

    /** Increments. @version 1 */
    export const inc = (x: number): number => x + 1;

    export const undocumented = () => 2;

    export class Counter {
      /** Bumps the count. @version 1 */
      bump(): void {}

      /** A field arrow. @version 1 */
      reset = (): void => {};
    }

    interface I { m(): void; }
    export default function () {}
    declare function external(): number;
"""


class TestJsDocBlocks:
    def test_functions_found_and_named(self):
        functions = _parse("typescript", TS)
        assert set(functions) == {"add", "inc", "undocumented", "bump", "reset"}
        assert functions["bump"].enclosing_class == "Counter"
        assert functions["reset"].enclosing_class == "Counter"

    def test_jsdoc_is_found_above_export_and_const(self):
        functions = _parse("typescript", TS)
        assert functions["add"].doxygen.tags["version"] == ["2"]
        assert functions["inc"].doxygen.tags["version"] == ["1"]
        assert functions["undocumented"].doxygen is None

    def test_summary_is_the_brief(self):
        functions = _parse("typescript", TS)
        assert functions["add"].doxygen.tags["brief"] == ["Adds one."]
        assert functions["inc"].doxygen.tags["brief"] == ["Increments."]

    def test_plain_comment_is_not_jsdoc(self):
        functions = _parse(
            "javascript", "// not jsdoc\nfunction f() {}\n/*** banner */\nfunction g() {}\n"
        )
        assert functions["f"].doxygen is None and functions["g"].doxygen is None

    def test_return_annotation_decides_void(self):
        functions = _parse("typescript", TS)
        assert functions["add"].returns_void is False
        assert functions["bump"].returns_void is True
        assert _parse("typescript", "async function f(): Promise<void> {}\n")["f"].returns_void
        assert _parse("javascript", "function f() { return 1; }\n")["f"].returns_void

    def test_tsx_parses_jsx(self):
        src = "/** Renders. @version 1 */\nexport function App() { return <div>{x}</div>; }\n"
        functions = _parse("tsx", src)
        assert functions["App"].doxygen.tags["brief"] == ["Renders."]


class TestJsTsValidation:
    def test_opt_in(self, tmp_path):
        source = tmp_path / "a.ts"
        source.write_text(dedent(TS))
        assert validate_file(str(source), CONFIG_DEFAULTS, no_git=True) == []

    def test_violations(self, tmp_path):
        source = tmp_path / "a.ts"
        source.write_text(dedent(TS))
        messages = [v.message for v in validate_file(str(source), _config(), no_git=True)]
        assert len(messages) == 1, messages
        assert "'undocumented' has no doxygen comment" in messages[0]
        assert "JSDoc" in messages[0]

    def test_require_return_bites_only_on_valued_annotations(self, tmp_path):
        source = tmp_path / "a.ts"
        source.write_text(dedent(TS))
        config = _config(typescript={"require_return": True})
        messages = [v.message for v in validate_file(str(source), config, no_git=True)]
        returns = [m for m in messages if "@return" in m]
        assert len(returns) == 2, messages  # add and inc return number; bump/reset are void

    @pytest.mark.parametrize("name", ["a.js", "a.mjs", "a.cjs", "a.jsx"])
    def test_javascript_extensions(self, tmp_path, name):
        source = tmp_path / name
        source.write_text("export function f() {}\n")
        (violation,) = validate_file(str(source), _config(), no_git=True)
        assert "'f' has no doxygen comment" in violation.message

    def test_tsx_file_uses_typescript_config(self, tmp_path):
        assert language_for_file("App.tsx", {}) == "tsx"
        source = tmp_path / "App.tsx"
        source.write_text("export function App() { return <div/>; }\n")
        (violation,) = validate_file(str(source), _config(), no_git=True)
        assert "'App'" in violation.message
