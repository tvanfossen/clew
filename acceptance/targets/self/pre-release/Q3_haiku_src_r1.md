# Q3 — src — haiku — run 1

## Answer

This program (doxyguard-db) searches for configuration files belonging to **doxygen** (the external tool it drives, for documentation extraction) and **doxygen-guard** (a pre-commit gate the repo may adopt). Here's everywhere it looks and the outcomes:

---

## **Doxyfile Search** (doxygen's configuration)

**Locations searched (in order):** `discover_doxyfile` at doxygen.py:189-234

1. `repo_root / "Doxyfile"` — doxygen.py:231
2. `repo_root / "docs" / "Doxyfile"` — doxygen.py:231 (via `_DOXYFILE_DIRS`)
3. `repo_root / "doc" / "Doxyfile"` — doxygen.py:231

**Files found but NOT used:** `rejected_doxyfile_candidates` at doxygen.py:280-297
- Any `*/Doxyfile` outside the trusted locations (root, `docs/`, `doc/`)
- These are deliberately refused with a logged message doxygen.py:362-374
- The reasoning: discovery was "caught selecting a TEST FIXTURE's Doxyfile to index a whole project" (doxygen.py:203)

---

## **Doxygen-Guard Config Search** (doxygen-guard's configuration)

**Locations searched (in order):** `discover_guard_config` at precommit.py:317-351

1. **Explicit path** — if `--guard-config` passed (now `explicit` parameter, precommit.py:341-344), wins immediately
2. **Repo root** — `repo_root / ".doxygen-guard.yaml"` via `_guard_config_at_root` (precommit.py:180-183)
3. **Hook args** — reads `.pre-commit-config.yaml` (precommit.py:229), finds the `doxygen-guard` hook (precommit.py:87-89), extracts `--config` flag value via `_config_arg` (precommit.py:191-206)
4. **Conventional dirs** — searches `conf/`, `config/`, `.config/` (precommit.py:51) with names `doxygen-guard.yaml` or `.doxygen-guard.yaml` (precommit.py:52)

**Files found but NOT used:** 
- When multiple candidates exist in conventional directories, **none are adopted** (precommit.py:277-297)
- Logs a warning naming all candidates and advises using the hook's `--config` arg to disambiguate (precommit.py:287-296)

---

## **.doxyguard-db.yaml Search** (doxyguard-db's own declarations)

**Locations searched (in order):** `load_declaration_located` at declaration.py:279-337

1. `repo_root / ".doxyguard-db.yaml"` — declaration.py:310
2. If absent, the `x-doxyguard-db` section of discovered guard config — `_passthrough_declaration` (declaration.py:523-574)

**Files found but NOT used:**
- If the document is unreadable or malformed YAML, logged at WARNING and treated as absent (declaration.py:345-357)
- Section with unknown name: raises `DeclarationError` immediately, refusing silently-wrong behavior (declaration.py:328-335, vocabulary.py:23-34)

---

## **Distinct Outcomes and Build Continuation**

### **Doxyfile Outcomes:**

| Outcome | Description | Build continues? | Code |
|---------|-------------|------------------|------|
| **Found at root** | Doxyfile in `repo_root/Doxyfile` | **YES** | doxygen.py:231-234 |
| **Found in docs/** | Doxyfile in `repo_root/docs/Doxyfile` | **YES** | doxygen.py:231 |
| **Found in doc/** | Doxyfile in `repo_root/doc/Doxyfile` | **YES** | doxygen.py:231 |
| **Stray Doxyfiles found** | Found outside trusted locations (e.g., `sample/Doxyfile`) | **YES** — synthesis used instead | doxygen.py:362-374; `DOXYFILE_REJECTED` |
| **None found** | No Doxyfile anywhere | **YES** — synthesis used | doxygen.py:381-389; `DOXYFILE_ABSENT` |
| **Explicit --doxyfile missing** | User passed `--doxyfile <path>` but it doesn't exist | **NO** — FATAL | doxygen.py:333-341; `DOXYFILE_EXPLICIT_MISSING` in `_DOXYFILE_FATAL_SITUATIONS` at doxygen.py:402 |
| **Neither --doxyfile nor --repo-root given** | No input whatsoever | **NO** — FATAL | doxygen.py:348-355; `DOXYFILE_NO_TARGET` in `_DOXYFILE_FATAL_SITUATIONS` at doxygen.py:402 |

### **Guard Config Outcomes:**

| Outcome | Build continues? | Code |
|---------|------------------|------|
| **Found at root** | **YES** | precommit.py:180-183 |
| **Found via hook args** | **YES** | precommit.py:214-245 |
| **Found in conventional dir (unambiguous)** | **YES** | precommit.py:253-297 |
| **Multiple candidates in conventional dirs** | **YES** — none adopted, defaults used, WARNING logged | precommit.py:277-297 |
| **Not found anywhere** | **YES** — built-in defaults used, WARNING logged | precommit.py:376-386 |

### **.doxyguard-db.yaml Outcomes:**

| Outcome | Build continues? | Code |
|---------|------------------|------|
| **Found in repo root** | **YES** | declaration.py:310-311 |
| **Found in guard config passthrough** | **YES** | declaration.py:326; `_passthrough_declaration` |
| **Not found** | **YES** — empty dict `{}`, built-in defaults used | declaration.py:308, 312 |
| **Unreadable or malformed YAML** | **YES** — WARNING logged, treated as absent | declaration.py:345-357 |
| **Valid YAML with unknown section name** | **NO** — raises `DeclarationError` | declaration.py:328-335 |

---

## **Key Behaviors**

**Refusal to guess:** Guard config discovery in conventional directories will refuse (not guess) when multiple candidates exist (precommit.py:253-297). Similarly, `discover_doxyfile` refuses strays (doxygen.py:189-234). Both require explicit declaration.

**Graceful degradation:** Missing configurations degrade to built-in defaults with logged warnings, not errors. The exception: unknown section names in a declaration that parses successfully — these raise an exception because a misspelled section names the author's intent but corrupts silently (declaration.py:328-335).

**Synthesis as fallback:** When no Doxyfile is found (either not present, or stray candidates refused), the program synthesizes one from the declared index scope or the whole repository (doxygen.py:454+).

---

## Gaps

None identified. The search order, behavior on ambiguity/absence, and build-continuation status are fully traceable in the cited code paths.
