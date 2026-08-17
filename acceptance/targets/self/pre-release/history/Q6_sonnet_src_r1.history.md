# Q6 — src — sonnet — run 1

> Machine-generated narrative of one benchmark cell. The authoritative record is the
> sibling `.transcript.jsonl`; this document exists so a reviewer can follow what the
> agent did without parsing JSON. If the two disagree, the JSONL is correct.

### 1. `Bash`
- **asked:** command=find ~/ddb-targets/self -iname "*.yaml" -o -iname "*.yml" | grep -v /.git | head -50
- **got:** ~/ddb-targets/self/acceptance/targets/entropic/questions.yaml ~/ddb-targets/self/acceptance/targets/self/questions.yaml ~/ddb-targets/self/acceptance/targets/mbedtls/questions.yaml ~/ddb-targets/self/acceptance/targets/m…

### 2. `Bash`
- **asked:** command=grep -rln "yaml.safe_load\|yaml.load\|DeclarationError\|load_declaration" ~/ddb-targets/self/doxyguard_db 2>/dev/null
- **got:** ~/ddb-targets/self/doxyguard_db/enrichment.py ~/ddb-targets/self/doxyguard_db/vocabulary.py ~/ddb-targets/self/doxyguard_db/buildoptions.py ~/ddb-targets/self/doxyguard_db/requirements.py ~/ddb-targets/self/doxyguard_db/…

### 3. `Read`
- **asked:** file_path=~/ddb-targets/self/doxyguard_db/declaration.py
- **got:** 1	# SPDX-License-Identifier: MIT 2	"""A target repo's own `.doxyguard-db.yaml` — its declared indexing conventions. 3	 4	doxyguard-db's central mandate is built-in defaults plus a DECLARED override, never a 5	hardcoded a…

### 4. `Bash`
- **asked:** command=grep -n "_reject_unknown\|DeclarationError\|def load\|key_arg_idx\|key_arg_index" ~/ddb-targets/self/doxyguard_db/dispatch.py | head -60
- **got:** 50:          key_arg_index: 0 78:from .vocabulary import KEY_DIRECTION, DeclarationError, declaration_origin 93:## author's declaration did nothing. The same applies one level down: `key_arg_idx` 94:## for `key_arg_index…

### 5. `Read`
- **asked:** file_path=~/ddb-targets/self/doxyguard_db/dispatch.py
- **got:** 1	# SPDX-License-Identifier: MIT 2	"""The indirect-dispatch DECLARATION — a repo's own map of its indirections. 3	 4	The static graph recovers a relationship only when both endpoints are named at 5	the site. A call edge …

### 6. `Read`
- **asked:** file_path=~/ddb-targets/self/doxyguard_db/dispatch.py
- **got:** 395	    @version 3 396	    """ 397	    if source is None: 398	        return None 399	    if isinstance(source, dict): 400	        return source 401	    import yaml 402	 403	    data = yaml.safe_load(Path(source).read_te…

### 7. `Bash`
- **asked:** command=grep -rn "DeclarationError" ~/ddb-targets/self/doxyguard_db/vocabulary.py ~/ddb-targets/self/doxyguard_db/cli.py ~/ddb-targets/self/doxyguard_db/mcp_server*/*.py 2>/dev/null
- **got:** ~/ddb-targets/self/doxyguard_db/vocabulary.py:39:`DeclarationError`), rather than normalizing to 'unknown' as the loaders used ~/ddb-targets/self/doxyguard_db/vocabulary.py:65:class DeclarationError(ValueError): ~/ddb-ta…

### 8. `Read`
- **asked:** file_path=~/ddb-targets/self/doxyguard_db/cli.py
- **got:** 2370	 2371	 2372	## @brief Entry point — dispatch a subcommand, else parse args and build. 2373	## @version 14 2374	## @req REQ-DDB-CLI-001 2375	def main() -> None: 2376	    """Entry point — parse args, run doxygen, opti…

### 9. `Bash`
- **asked:** command=grep -rln "DeclarationError\|BuildOptionError" ~/ddb-targets/self/doxyguard_db/mcp_server 2>/dev/null; find ~/ddb-targets/self/doxyguard_db -iname "*mcp*"
- **got:** ~/ddb-targets/self/doxyguard_db/mcp_config.py ~/ddb-targets/self/doxyguard_db/mcp_server

### 10. `Bash`
- **asked:** command=ls ~/ddb-targets/self/doxyguard_db/mcp_server; echo ---; grep -rn "build_or_refresh\|except.*Error\|try:" ~/ddb-targets/self/doxyguard_db/mcp_server/*.py | grep -i "error\|except" | head -40
- **got:** descriptions descriptions.py emptiness.py freshness.py __init__.py __main__.py _sdk.py server.py state.py tools_query.py --- ~/ddb-targets/self/doxyguard_db/mcp_server/descriptions.py:97:    except json.JSONDecodeError a…

### 11. `Read`
- **asked:** file_path=~/ddb-targets/self/doxyguard_db/mcp_server/state.py
- **got:** 370	        self.home = home if home is not None else state_home() 371	        self.path = self.home / REGISTRY_NAME 372	 373	    ## @brief Load the raw registry mapping from disk. 374	    ## @return Dict of repo_path → …

### 12. `Bash`
- **asked:** command=grep -n "def build_or_refresh\|def _build\|build_index\|except" ~/ddb-targets/self/doxyguard_db/mcp_server/server.py | head -60
- **got:** 103:as an exception carrying a traceback rather than as an exit code plus whatever 104:reached a pipe. The exception is caught at the tool boundary, so a failed build 380:        except Exception: 387:## @param exc The e…

### 13. `Read`
- **asked:** file_path=~/ddb-targets/self/doxyguard_db/mcp_server/server.py
- **got:** 85	call, visible in the request and echoed in the reply's `target` field. Moving to the SDK's 86	`Resolve`/`ListRoots` resolver marker is still declined: it would buy transport-correctness 87	on 2026-07-28+ connections f…

### 14. `Read`
- **asked:** file_path=~/ddb-targets/self/doxyguard_db/mcp_server/server.py
- **got:** 1440	        # A missing Doxyfile is never fatal here: under `from-guard` the pipeline 1441	        # synthesizes one from a declared `index_scope:`, and a repo that declares 1442	        # nothing gets the whole-repo ti…

### 15. `Bash`
- **asked:** command=grep -n "_failure_result" -A 20 ~/ddb-targets/self/doxyguard_db/mcp_server/server.py | head -30
- **got:** 392:def _failure_result(exc: BaseException, rendered: str) -> dict[str, Any]: 393-    """In-process the outcome IS the exception, so it is reported as one: type and 394-    message on `error`, the full traceback beside i…

### 16. `Read`
- **asked:** file_path=~/ddb-targets/self/doxyguard_db/dispatch.py
- **got:** 270	## @param entry The declaration entry mapping. 271	## @param field Field name to read. 272	## @param owner Where the entry was declared, for the error message. 273	## @return The field's string value. 274	## @version…

**Reasoning.** Now let me check the requirements.yaml catalog handling too, since that's another manifest with its own key vocabulary and error behavior, plus how a totally invalid YAML file behaves there.

### 17. `Bash`
- **asked:** command=grep -n "def load\|DeclarationError\|safe_load\|except\|logger.warning\|logger.error" ~/ddb-targets/self/doxyguard_db/requirements.py | head -50
- **got:** 100:def load_guard_config( 390:    data = yaml.safe_load(requirements_yaml.read_text(encoding="utf-8")) 706:        logger.warning(

### 18. `Read`
- **asked:** file_path=~/ddb-targets/self/doxyguard_db/requirements.py
- **got:** 360	    nothing else is guessed: 361	 362	      * the flat `[{id, ...}, ...]` list — CSV semantics in YAML syntax, keyed by the 363	        declared `impact.requirements.{id_column,name_column}` mapping when the guard 36…

### 19. `Bash`
- **asked:** command=grep -n "ingest_requirements\|import_requirements" ~/ddb-targets/self/doxyguard_db/cli.py
- **got:** 51: 15. ingest_requirements_yaml (optional --requirements) 152:    ingest_requirements_yaml, 1599:    ingest_requirements_yaml(output, requirements_yaml, guard_cfg)

### 20. `Read`
- **asked:** file_path=~/ddb-targets/self/doxyguard_db/cli.py
- **got:** 2428	    except (DeclarationError, BuildOptionError) as exc: 2429	        logger.error("invalid declaration — %s", exc) 2430	        sys.exit(2) 2431	    except DoxygenUnavailableError as exc: 2432	        # Same treatme…

### 21. `Bash`
- **asked:** command=grep -n "_reject_unknown\|DeclarationError\|KEYS = frozenset\|def load" ~/ddb-targets/self/doxyguard_db/shared_key_edges.py ~/ddb-targets/self/doxyguard_db/threads.py ~/ddb-targets/self/doxyguard_db/locks.py 2>/dev/null
- **got:** ~/ddb-targets/self/doxyguard_db/shared_key_edges.py:487:def load_shared_key_patterns( ~/ddb-targets/self/doxyguard_db/threads.py:268:def load_thread_patterns(path: Path | dict | None) -> list[SpawnPattern]: ~/ddb-targets…

### 22. `Read`
- **asked:** file_path=~/ddb-targets/self/doxyguard_db/threads.py
- **got:** 260	] 261	 262	 263	## @brief Load --thread-patterns YAML, merged over the built-in defaults. 264	## @param path Path to the YAML file, or None to use only the defaults. 265	## @return Merged spawn-pattern list (loaded e…

**Reasoning.** ## Answer

The behavior depends on which of the two structural levels the mistyped key sits at, and on which manifest it's in — the pipeline is not uniform across all of them.

### Document level — `.doxyguard-db.yaml`'s own top-level section names

`load_declaration_located` reads the file into a mapping (`doxyguard_db/declaration.py:279-337`), then checks every top-level key against a fixed allow-list, `KNOWN_SECTIONS` (`doxyguard_db/declaration.py:234-252`, e.g. `shared_key_patterns`, `thread_patterns`, `dispatch`, `locks`, …). If your colleague writes `shared_key_pattern` (singular) instea

---

## Final answer as submitted

## Answer

The behavior depends on which of the two structural levels the mistyped key sits at, and on which manifest it's in — the pipeline is not uniform across all of them.

### Document level — `.doxyguard-db.yaml`'s own top-level section names

`load_declaration_located` reads the file into a mapping (`doxyguard_db/declaration.py:279-337`), then checks every top-level key against a fixed allow-list, `KNOWN_SECTIONS` (`doxyguard_db/declaration.py:234-252`, e.g. `shared_key_patterns`, `thread_patterns`, `dispatch`, `locks`, …). If your colleague writes `shared_key_pattern` (singular) instead of `shared_key_patterns`, that check fails:

```
unknown = sorted(str(key) for key in data if key not in KNOWN_SECTIONS)
if unknown:
    raise DeclarationError(...)
```
(`doxyguard_db/declaration.py:328-335`)

This is a deliberate fail-closed design, not an accident: the module docstring explains that without it, "a singular/plural slip … parses to a perfectly valid YAML mapping that NO consumer reads, so the build runs entirely on built-in defaults — while `load_declaration` logs 'declares shared_key_pattern' and tells the owner their file was honoured" (`doxyguard_db/declaration.py:219-227`). So a mistyped section name is refused outright rather than silently ignored.

### Entry level — keys inside one section's list entries

The same fail-closed policy is applied one level down, inside individual sections. `dispatch.py`'s `dispatch_tables`/`interfaces`/`shared_key_wrappers` entries each have their own allowed-key set (`_INTERFACE_KEYS`, `_TABLE_KEYS`, `_WRAPPER_KEYS`, `doxyguard_db/dispatch.py:97-99`), checked by `_reject_unknown` (`doxyguard_db/dispatch.py:109-121`) when each entry is parsed (`doxyguard_db/dispatch.py:327,354,375`). Writing `key_arg_idx` instead of `key_arg_index` in a `shared_key_wrappers` entry raises the same `DeclarationError`, naming the offending key and the allowed set. The module docstring is explicit about why this exists: an entry-level typo "does not produce 'no dataflow' but the WRONG dataflow, from a typo" (`doxyguard_db/dispatch.py:93-95`) — worse than the document-level slip because it's quieter.

Other manifests validate individual *values* the same way rather than key names — e.g. `load_thread_patterns`' `kind` field and `load_lock_patterns`' `form`/`kind`/`role`/`mode` each raise `DeclarationError` on an unrecognized token (`doxyguard_db/threads.py:286-290`, `doxyguard_db/locks.py:206`).

### Where the raised error goes

`DeclarationError` (a `ValueError` subclass, `doxyguard_db/vocabulary.py:65`) propagates up out of the build:
- **CLI** (`python -m doxyguard_db`): caught in `main()`, logged as one line (`"invalid declaration — %s"`) instead of a traceback, and the process exits with code 2 (`doxyguard_db/cli.py:2426-2430,2390-2394`).
- **MCP server** (`build_or_refresh`): `build_index` is called inside a `try/except (Exception, SystemExit)`; the exception is caught at the tool boundary and returned as `{"ok": False, "error": "DeclarationError: ...", ...}` via `_failure_result`, without taking the server down (`doxyguard_db/mcp_server/server.py:1465-1481`, `doxyguard_db/mcp_server/server.py:392-411`).

Either way: **the build refuses to run** rather than quietly falling back to built-in defaults.

### The contrasting manifest: `requirements.yaml`

Not every manifest enforces this. The requirements catalog is explicitly *not* fail-closed on shape: `ingest_requirements_yaml` tries a flat list, then a `requirements:`-keyed mapping, and if neither matches (e.g. `requirement:` singular, or any other shape) it just logs at **INFO** — "neither a flat id-bearing list nor a `requirements:` mapping … ingesting 0 catalog rows" — and moves on (`doxyguard_db/requirements.py:393-403`). This is a deliberate difference: "there is NO universal requirements.yaml format" so the catalog is optional metadata, and `@req` tag edges (not this catalog) are the authoritative traceability (`doxyguard_db/declaration.py:98-105`, `doxyguard_db/requirements.py:370-376`).

### A correctly written file

When every section name and every entry key matches, `load_declaration_located` logs `"declaration: %s declares %s"` naming the sections read (`doxyguard_db/declaration.py:336`), and each section's loader (e.g. `load_dispatch_manifest`, `doxyguard_db/dispatch.py:437-439`) logs how many entries it accepted. The declared values **replace or override the built-in defaults** for that section (e.g. dispatch bindings/tables/wrappers are added to the causal graph; event-tag vocabulary is fully replaced, not merged — `doxyguard_db/declaration.py:451-463`). No error, no refusal — the build proceeds using the stated conventions.

### A file that isn't valid YAML at all

This is a **different failure mode**, and for `.doxyguard-db.yaml` specifically it degrades rather than refusing. `_read_mapping` wraps the parse in `try/except (OSError, yaml.YAMLError)`; on a syntax error (or a non-mapping document) it logs at **WARNING** — `"%s is unreadable (%s) — ignoring it, using defaults"` — and returns `{}` (`doxyguard_db/declaration.py:345-357`). `load_declaration_located` then treats that as "nothing declared" and the build proceeds silently on built-in defaults, with no `DeclarationError` and no exit-2.

So the asymmetry is real and intentional: **syntactically broken YAML degrades quietly to defaults; syntactically valid YAML with a misspelled key is refused loudly.** The docstring names this explicitly: "Unparseable YAML is an accident with nothing recoverable in it. A misspelled section is a document that parses, where the author plainly intended something" (`doxyguard_db/declaration.py:294-301`).

This is different again for a standalone manifest passed as a path (e.g. `--dispatch some.yaml`) — `_document`'s `yaml.safe_load` there has no surrounding `try/except` (`doxyguard_db/dispatch.py:401-406`), so a syntax error in that file would raise `yaml.YAMLError` uncaught rather than degrade — and likewise `ingest_requirements_yaml`'s `yaml.safe_load` call has no try/except around it either (`doxyguard_db/requirements.py:390`), so invalid YAML in `requirements.yaml` propagates as an uncaught exception through `cli.py:1599`, which `main()`'s `except (DeclarationError, BuildOptionError)`/`except DoxygenUnavailableError` clauses do **not** catch (`doxyguard_db/cli.py:2426-2437`) — meaning it would surface as a full traceback and Python's default exit code, not the clean exit-2 path.

## Gaps

- I did not trace `.doxygen-guard.yaml`'s own key validation (owned by the external `doxygen-guard` package, only its `x-doxyguard-db` passthrough section is this repo's concern) — out of scope for "this program['s]" own manifests but worth flagging if the colleague's typo is in the *gate's* section rather than the passthrough.
- I did not exhaustively confirm whether `load_shared_key_patterns` (`shared_key_edges.py:487`) enforces an entry-level `_reject_unknown` the way `dispatch.py` does — I read only its signature, not its body, so I can't confirm the shared-key-patterns manifest behaves identically to dispatch's entry-level fail-closed behavior; this should be verified before generalizing the entry-level claim to every section.
- `declaration.string_list` (used for `entry_patterns`/`vendored`) behaves differently again — a malformed (non-list) section there **warns and degrades to `[]`** rather than raising (`doxyguard_db/declaration.py:436-442`), which I did not reconcile against the "fail closed" framing above; it's a third distinct behavior worth knowing about if the mistyped key lands there.
