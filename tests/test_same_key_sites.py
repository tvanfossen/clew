# SPDX-License-Identifier: MIT
"""A property key a function writes leads to the few other symbols that define it (F1-mm; 2.0.0).

FOUND BY THE 2.0.0 UNDERPERFORMANCE REVIEW (mattermost F1, Q1 m2). Every winning cell, shell or
index, followed the key `buildRequestOptions` writes (`requestOptions.retryPolicyConfiguration =
{retryLimit: 0}`) to where its default is set, `NetworkManager.DEFAULT_CONFIG`
(`network_manager.ts:68`, `retryLimit: 3`). Every losing index cell read that line and stopped: the
dossier said `writes: []`, and nothing pointed at the other definition. The shared-key layer is the
C/Python analogue and holds 0 rows on that repository.

`same_key_sites` lists, for each key the function writes (an object-literal key or a
`x.key = ...` assignment), the OTHER symbols outside test files whose literals or assignments carry
the same key. RARITY-GATED: a key held by more than `KEY_RARITY` other non-test symbols (`headers`,
`body`) is left out, because a list of every object with a `headers` field points nowhere.

@brief Tests same-key sites on function dossiers.
@version 1
"""

from __future__ import annotations

from pathlib import Path

import pytest

from clew.cli import _build_argparser, _run_pipeline
from clew.query.subject import dossier

_TRACKING = """\
export class Client {
    buildRequestOptions(options: any) {
        const requestOptions: any = {body: options.body, headers: {}};
        if (options.noRetry) {
            requestOptions.retryPolicyConfiguration = {retryLimit: 0};
        }
        return requestOptions;
    }
}
"""
_MANAGER = """\
export class NetworkManager {
    private DEFAULT_CONFIG = {
        headers: {},
        retryPolicyConfiguration: {
            retryLimit: 3,
        },
    };
}
"""
_TEST_HELPER = (
    "export function createClient() {\n    return {retryPolicyConfiguration: {retryLimit: 1}};\n}\n"
)


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    """@brief Index the mattermost-shaped repo. @return (db, repo)."""
    base = tmp_path_factory.mktemp("keys")
    repo = base / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "test").mkdir()
    (repo / "src/tracking.ts").write_text(_TRACKING)
    (repo / "src/network_manager.ts").write_text(_MANAGER)
    (repo / "test/test_helper.ts").write_text(_TEST_HELPER)
    ## `headers` in five more non-test holders: six in all besides the subject, over the gate.
    for i in range(5):
        (repo / f"src/h{i}.ts").write_text(
            f"export function h{i}() {{\n    return {{headers: {{}}}};\n}}\n"
        )
    db = base / "clew.db"
    _run_pipeline(_build_argparser().parse_args(["--output", str(db), "--repo-root", str(repo)]))
    return db, repo


def _sites(built, name: str) -> list[tuple]:
    """@brief (key, holder, file, line). @return Rows."""
    db, repo = built
    fn = dossier(db, name, repo_root=repo).function
    return [(s.key, s.holder, s.file, s.line) for s in fn.same_key_sites]


def test_a_written_key_leads_to_its_default(built) -> None:
    """@brief retryPolicyConfiguration and retryLimit both lead to DEFAULT_CONFIG; nothing else."""
    assert _sites(built, "buildRequestOptions") == [
        ("retryLimit", "DEFAULT_CONFIG", "src/network_manager.ts", 5),
        ("retryPolicyConfiguration", "DEFAULT_CONFIG", "src/network_manager.ts", 4),
    ]


def test_test_files_and_common_keys_are_left_out(built) -> None:
    """@brief No test_helper site; no `headers` (six other holders, over KEY_RARITY)."""
    rows = _sites(built, "buildRequestOptions")
    assert all(f != "test/test_helper.ts" for _k, _h, f, _l in rows)
    assert all(k != "headers" for k, _h, _f, _l in rows)
