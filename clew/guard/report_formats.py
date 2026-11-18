# SPDX-License-Identifier: MIT
"""Machine-readable renderings of guard violations: SARIF 2.1.0, GitLab Code Quality, GitHub
workflow commands (S1; 2.0.0).

OWNER-APPROVED 2026-11-17 (standards research, S1). `clew guard validate` printed one
`file:line: [check] message` line per violation to stderr, which a human reads and no code
host can annotate. These three formats are what GitHub code scanning, GitLab merge-request
widgets and GitHub Actions annotations consume.

A FINGERPRINT THAT SURVIVES A LINE MOVE. Code hosts de-duplicate results across runs by
fingerprint; one built from the line number makes every edit above a function look like a new
violation and the old one fixed. The fingerprint here is built from the check, the file, the
function's qualified identity (class, name and parameter list, so overloads stay distinct) and
the message — none of which moves when a line is inserted above.

COMPLEXITY IS NOT HERE. Cognitive complexity and return counts are a separate pre-commit hook,
not a guard check, so these outputs do not carry them (stated in GUARD.md).

@brief Guard violations as SARIF, GitLab Code Quality and GitHub annotations.
@version 1
"""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .checks import Violation

## The formats `clew guard validate --format` accepts besides the default human text.
FORMATS = ("text", "sarif", "gitlab", "github")
## The SARIF schema and version this module writes.
SARIF_SCHEMA = "https://json.schemastore.org/sarif-2.1.0.json"
SARIF_VERSION = "2.1.0"
## What each check class means, for a SARIF rule's short description.
RULE_TEXT = {
    "presence": "A function or file lacks the required doxygen block or tag.",
    "version": "A function's body changed and its version tag did not.",
    "tag": "A doxygen tag's value is unknown, malformed, duplicated or unresolvable.",
    "coverage": "A function carries no requirement tag where one is required.",
    "bus": "A function that crosses a bus does not declare it.",
}
## The tool's name as every format reports it.
TOOL_NAME = "clew guard"


## @brief A violation's fingerprint: stable when lines move, distinct across overloads.
## @param v The violation.
## @return Hex digest.
## @version 1
## @req REQ-DDB-GUARD-001
def fingerprint(v: Violation) -> str:
    """No line number goes in: see the module docstring.

    @brief Fingerprint one violation.
    @return Hex digest.
    """
    key = "\x1f".join((v.check, v.file, v.qualified, v.message))
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


## @brief Base renderer: one document built from per-violation records.
## @version 1
class ViolationRenderer:
    """THE TEMPLATE: `render` orders violations deterministically, builds one record each and
    wraps them. A format states only its record and its wrapper.

    @brief Base class for violation output formats.
    @version 1
    """

    ## @brief Render every violation as one document.
    ## @param violations The violations, in any order.
    ## @return The document text, newline-terminated.
    ## @version 1
    ## @req REQ-DDB-GUARD-001
    def render(self, violations: list[Violation]) -> str:
        """Sorted by (file, line, check, message), so the same violations always render the
        same bytes.

        @brief Render a document.
        @return Text.
        """
        ordered = sorted(violations, key=lambda v: (v.file, v.line, v.check, v.message))
        return self.wrap([self.record(v) for v in ordered], ordered)

    ## @brief One violation's record.
    ## @param v The violation.
    ## @return The record (format-specific).
    ## @version 1
    ## @dg_internal
    def record(self, v: Violation) -> object:
        """@brief Per-violation record. @return Record."""
        raise NotImplementedError

    ## @brief The document around the records.
    ## @param records Per-violation records, in order.
    ## @param violations The violations they came from, in the same order.
    ## @return The document text.
    ## @version 1
    ## @dg_internal
    def wrap(self, records: list, violations: list[Violation]) -> str:
        """@brief Default: a JSON array. @return Text."""
        return json.dumps(records, indent=2, sort_keys=True) + "\n"


## @brief SARIF 2.1.0: one run, one rule per check class, one result per violation.
## @version 1
class SarifRenderer(ViolationRenderer):
    """@brief SARIF output.
    @version 1
    """

    ## @brief One SARIF result.
    ## @param v The violation.
    ## @return The result object.
    ## @version 1
    ## @dg_internal
    def record(self, v: Violation) -> object:
        """@brief SARIF result. @return Dict."""
        return {
            "ruleId": v.check,
            "level": "error",
            "message": {"text": v.message},
            "locations": [
                {
                    "physicalLocation": {
                        "artifactLocation": {"uri": v.file},
                        "region": {"startLine": max(v.line, 1)},
                    },
                    **(
                        {"logicalLocations": [{"fullyQualifiedName": v.qualified}]}
                        if v.qualified
                        else {}
                    ),
                }
            ],
            "partialFingerprints": {"clewGuard/v1": fingerprint(v)},
        }

    ## @brief The SARIF log around the results.
    ## @param records The results.
    ## @param violations The violations.
    ## @return The log text.
    ## @version 1
    ## @dg_internal
    def wrap(self, records: list, violations: list[Violation]) -> str:
        """Every check class the guard has is a rule, whether or not it fired, so a rule's
        index is stable across runs.

        @brief SARIF log.
        @return Text.
        """
        rules = [
            {"id": check, "shortDescription": {"text": text}}
            for check, text in sorted(RULE_TEXT.items())
        ]
        known = {r["id"] for r in rules}
        rules += [
            {"id": c, "shortDescription": {"text": c}}
            for c in sorted({v.check for v in violations} - known)
        ]
        log = {
            "$schema": SARIF_SCHEMA,
            "version": SARIF_VERSION,
            "runs": [{"tool": {"driver": {"name": TOOL_NAME, "rules": rules}}, "results": records}],
        }
        return json.dumps(log, indent=2, sort_keys=True) + "\n"


## @brief GitLab Code Quality: a JSON array of issues.
## @version 1
class GitLabRenderer(ViolationRenderer):
    """@brief GitLab Code Quality output.
    @version 1
    """

    ## @brief One Code Quality issue.
    ## @param v The violation.
    ## @return The issue object.
    ## @version 1
    ## @dg_internal
    def record(self, v: Violation) -> object:
        """@brief Code Quality issue. @return Dict."""
        return {
            "description": v.message,
            "check_name": v.check,
            "fingerprint": fingerprint(v),
            "severity": "major",
            "location": {"path": v.file, "lines": {"begin": max(v.line, 1)}},
        }


## @brief GitHub Actions workflow commands: one `::error` line per violation.
## @version 1
class GitHubRenderer(ViolationRenderer):
    """@brief GitHub annotation output.
    @version 1
    """

    ## @brief One `::error` workflow command.
    ## @param v The violation.
    ## @return The command line.
    ## @version 1
    ## @dg_internal
    def record(self, v: Violation) -> object:
        """Escaped as the runner requires: `%`, CR and LF everywhere; `:` and `,` also in a
        property value.

        @brief Workflow command.
        @return Text.
        """
        return (
            f"::error file={_prop(v.file)},line={max(v.line, 1)},title={_prop(f'{TOOL_NAME} {v.check}')}"
            f"::{_data(v.message)}"
        )

    ## @brief The command lines.
    ## @param records The lines.
    ## @param violations The violations.
    ## @return Text.
    ## @version 1
    ## @dg_internal
    def wrap(self, records: list, violations: list[Violation]) -> str:
        """@brief Join lines. @return Text."""
        return "".join(f"{r}\n" for r in records)


## @brief Escape a workflow command's message.
## @param text The text.
## @return Escaped text.
## @version 1
## @dg_internal
def _data(text: str) -> str:
    """@brief Escape data. @return Text."""
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


## @brief Escape a workflow command's property value.
## @param text The text.
## @return Escaped text.
## @version 1
## @dg_internal
def _prop(text: str) -> str:
    """@brief Escape a property. @return Text."""
    return _data(text).replace(":", "%3A").replace(",", "%2C")


## The renderer for each machine format.
RENDERERS: dict[str, type[ViolationRenderer]] = {
    "sarif": SarifRenderer,
    "gitlab": GitLabRenderer,
    "github": GitHubRenderer,
}


## @brief Render violations in a machine format.
## @param violations The violations.
## @param fmt One of `RENDERERS`.
## @return The document text.
## @version 1
## @req REQ-DDB-GUARD-001
def render(violations: list[Violation], fmt: str) -> str:
    """@brief Render in a named format. @return Text."""
    return RENDERERS[fmt]().render(violations)
