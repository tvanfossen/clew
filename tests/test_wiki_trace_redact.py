# SPDX-License-Identifier: MIT
"""Traced values published in the wiki carry no local paths (2.1 roadmap).

X-2 (2.0.0) put a recorded run's real values on the flow and test pages, and disclosed that a value
such as a `Path` carries the builder's absolute paths — `/home/<user>/…` — into a site meant to be
published. The repository's own path is `<repo>`, the builder's home `~`.

@brief Tests trace-value redaction.
@version 1
"""

from __future__ import annotations

import json
from pathlib import Path

from clew.wiki.tracerun import load_traces


def _span(value: str) -> dict:
    return {
        "resourceSpans": [
            {
                "scopeSpans": [
                    {
                        "spans": [
                            {
                                "name": "t",
                                "spanId": "1",
                                "parentSpanId": "",
                                "attributes": [
                                    {"key": "code.return", "value": {"stringValue": value}}
                                ],
                            }
                        ]
                    }
                ]
            }
        ]
    }


def test_the_repository_and_home_paths_are_redacted(tmp_path: Path, monkeypatch) -> None:  # noqa: ANN001
    """@brief `<repo>` for the repository, `~` for the home directory; the key untouched."""
    home = tmp_path / "home" / "dev"
    repo = home / "work" / "proj"
    (repo / "traces").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    value = f"[PosixPath('{repo}/src/a.py'), '{home}/.cache/x']"
    (repo / "traces" / "t.json").write_text(json.dumps(_span(value)))
    [(rel, otlp)] = load_traces(repo, ("traces/*.json",))
    attr = otlp["resourceSpans"][0]["scopeSpans"][0]["spans"][0]["attributes"][0]
    assert attr["key"] == "code.return"
    assert attr["value"]["stringValue"] == "[PosixPath('<repo>/src/a.py'), '~/.cache/x']"
    assert str(home) not in json.dumps(otlp)
