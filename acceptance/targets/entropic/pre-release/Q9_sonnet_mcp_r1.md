# Q9 — mcp — sonnet — run 1

## What entropic is

Entropic is a C++ agentic-LLM engine: a shared-library core (`librentropic.so`) that runs a local LLM (via a bundled `llama.cpp` submodule) as a stateful, tool-using agent loop, exposed through a pure-C API (`entropic.h`) and a CLI binary. It supports MCP tool servers (built-in and pluggable `.so` files), YAML-driven configuration/identities, SQLite-backed conversation storage, and speculative/MTP decoding on top of llama.cpp. `docs/architecture-cpp.md:1-21` is the project's own reference architecture and is authoritative — 48 numbered "Design Rules" entries there record real decisions with version/gh# provenance, not aspirational design.

## Where execution begins

There are two real entry points, not one:

1. **CLI binary** — `src/cli/main.cpp:111` (`int main(int argc, char* argv[])`). It's a thin dispatcher over a table of subcommands (`src/cli/main.cpp:93-97`, `anonymous_namespace{main.cpp}::Subcommand`, `src/cli/main.cpp:77-80`): `mcp-bridge` (`run_mcp_bridge`), `version`, `download`. Per the file's own doc comment (`src/cli/main.cpp:1-23`), `mcp-bridge` is the primary integration point — a consumer adds `entropic` to `.mcp.json` and the CLI relays JSON-RPC/stdio to an already-running engine's unix socket. **The CLI itself never creates an engine or loads a model** — that's Design Rule #36 (`docs/architecture-cpp.md:934`), confirmed by reading `main.cpp`: no call to `entropic_create` anywhere in it.
2. **The engine lifecycle, for whoever hosts it** (a TUI, a consumer app, the `examples/` programs) starts at `entropic_create` — `src/facade/entropic.cpp:241-266`. It allocates the opaque `entropic_engine` handle and does only Phase-0 init (logging, atomic log-id); subsystems stay null until `entropic_configure` — `src/facade/entropic.cpp:1749-1759` — parses the YAML/JSON config and builds them. The documented creation order (`docs/architecture-cpp.md:873-880`) is: types/logging → config loader → inference backend (model load deferred) → MCP server manager → core engine (`AgentEngine` + `ResponseGenerator` + `ContextManager` + `DirectiveProcessor`) → storage (optional) → hook registry. Destruction is the mirror order in `entropic_destroy`.

`AgentEngine::AgentEngine` — `src/core/engine.cpp:135-152` — is where the actual agent-loop object gets built: it wires `ContextManager`, `ResponseGenerator`, and `CompactionManager` together and registers directive handlers.

## Major subsystems (from the library decomposition, `docs/architecture-cpp.md:17-133`)

| `.so` | Responsibility | Key files seen in index |
|---|---|---|
| `librentropic-types` | Pure types, zero logic; universal dependency | `src/types/*` |
| `librentropic-core` | Engine loop, state machine, context mgmt, delegation, directives — **zero deps** on inference/mcp/storage/config | `src/core/engine.cpp` (29 symbols), `compactor_registry.cpp`, `identity_manager.cpp`, `constitutional_validator.cpp` |
| `librentropic-inference-{cuda,vulkan,cpu}` | llama.cpp-backed backend, adapters, sampler, speculative/MTP decode | `src/inference/llama_cpp_backend.{cpp,h}` (78+134 symbols — the largest single unit), `src/inference/orchestrator.cpp`, `adapters/` |
| `librentropic-mcp` + `-mcp-{filesystem,bash,git,diagnostics,web,entropic}` | Tool server base, registry, executor, permission manager, transport (stdio/SSE), per-server plugins | `src/mcp/server_base.cpp`, `tool_executor.cpp`, `permission_manager.cpp`, `servers/*.cpp` |
| `librentropic-config` | YAML config/schema validation, identity/constitution loading, bundled model registry | `src/config/loader.cpp` (40 symbols — largest config file) |
| `librentropic-storage` | SQLite conversation persistence, session logs, audit log | `src/storage/database.cpp`, `backend.cpp`, `audit_logger.cpp` |
| `librentropic` (facade) | Thin layer linking everything; the public C API | `src/facade/entropic.cpp` (149 symbols — by far the largest file in the repo) |

Every `.so` boundary is a **pure-C interface** (`include/entropic/interfaces/i_*.h`) — no `std::string`/vectors/vtables cross a library edge (Design Rule #2, `docs/architecture-cpp.md:900`). Internally each subsystem follows a three-layer pattern: C interface → concrete base with ~80% of the logic → thin implementation override (`docs/architecture-cpp.md:661-677`), e.g. `InferenceBackend` (base) → `LlamaCppBackend` (impl).

## Concurrency (from the lock/thread inventory, not narrative)

The index's thread search found 21 spawn sites total, but only **4 are first-party** (17 belong to the vendored `extern/llama.cpp`): `ExternalBridge::accept_loop` (`src/facade/external_bridge.cpp:796`), `HealthMonitor::monitor_loop` (`src/mcp/health_monitor.cpp:92`), `StdioTransport::stderr_reader_loop` (`src/mcp/transport_stdio.cpp:164`), `SSETransport::sse_reader_loop` (`src/mcp/transport_sse.cpp:107`). The lock inventory shows 97 distinct lock identities, 45 first-party — heaviest first-party users are `AdapterManager` (`src/inference/adapter_manager.cpp`, 11 acquisitions), `MCPAuthorizationManager` (`src/mcp/mcp_authorization.cpp`, 10), `AgentEngine::queue_mutex_` (`src/core/engine.cpp`, 5 acquisitions). Design Rule #10 ("atomic state, mutex transitions", `docs/architecture-cpp.md:908`) matches what's in `InferenceBackend`: `transition_mutex_` guards only lifecycle transitions, state reads are lock-free atomics.

## If you had to change something tomorrow

- **Adding/changing an MCP tool server**: `src/mcp/servers/*.cpp` + the plugin ABI in `include/entropic/interfaces/i_mcp_server.h` (`docs/architecture-cpp.md:222-291` walks the exact contract, including the two required exports).
- **Touching generation/inference behavior**: `src/inference/llama_cpp_backend.cpp` is the single biggest, most load-bearing file (78 symbols, 134 in its header) — read Design Rules #32-46 (`docs/architecture-cpp.md:930-946`) first; speculative/MTP decoding has had multiple hard-won correctness fixes (recurrent-model gating, GQA/flash-attn aborts, lossless-at-any-temperature proof) that are easy to silently regress.
- **Config/identity changes**: `src/config/loader.cpp` (40 symbols) is the biggest src/config file; config resolution order is documented (`docs/architecture-cpp.md:694-698`: compiled defaults → global → project → env vars).
- **CLI/bridge changes**: `src/cli/main.cpp` is intentionally minimal — do not add engine/model logic there (Design Rule #36 is an explicit "forbidden by design").

## Coverage of this answer

- The index holds **2,132 files** total; of those, **`extern/` (llama.cpp submodule) accounts for 1,237 indexed + 49,705 files marked external** — i.e. the vast majority of the physical tree is vendored inference code this answer treats as a dependency, not a subsystem to describe in depth.
- This-repository's own code is small by comparison: `src/` 112 files (1,105 symbols), `include/` 89 files (1,678 symbols), `tests/` 218 files (1,565 symbols), `examples/` 24, `python/` 11.
- I read/queried: `src/cli/main.cpp` in full, `docs/architecture-cpp.md` in full, and dossiers for `entropic_create`, `entropic_configure`, `AgentEngine::AgentEngine`, plus the thread and lock inventories and the file/symbol rollup.
- I did **not** read `src/facade/entropic.cpp` (149 symbols, the largest file — the C API surface) or `src/inference/llama_cpp_backend.{cpp,h}` (the largest inference unit) beyond what the index's dossier snippets showed; a real "make a change tomorrow" pass on either of those should start with `dossier` on the specific function being touched.
- The root directory shows **418 indexed / 413 "unresolved"** — these are almost certainly CMake/build/config files with no grammar the indexer parses (CMakeLists.txt, CMakePresets.json, etc.); I did not open the CMake build to verify target names against `docs/architecture-cpp.md`'s CMake options table.

## Gaps

- The doc's class names for the config/identity layer (`IdentityManager`, `ConstitutionalValidator`, `CompactorRegistry`) were confirmed only via lock-scope metadata (`scope: class:X`), not by dossiering each class directly — I did not verify their public interfaces.
- `ModelOrchestrator` (`include/entropic/inference/orchestrator.h`) and the speculative/MTP decode path are described from `docs/architecture-cpp.md` design-rule prose only; I did not read `src/inference/orchestrator.cpp` or `llama_cpp_backend.cpp` bodies to independently confirm the current MTP guard logic still matches rules #42–50.
- A bare `dossier("main")` call resolves ambiguously to an unrelated `main()` inside `extern/llama.cpp/tools/parser/template-analysis.cpp` (the index has 8+ candidate `main` functions across the repo, all named identically) — I had to fall back to `search` + a direct `Read` of `src/cli/main.cpp` to get the real CLI entry point. This is the same class of name-collision limitation this project's own notes record for `_classify`/`_rows`-style helpers: don't trust a bare-name dossier for a common symbol name without checking `candidates`.
- CMake target-to-`.so` mapping (which CMakeLists actually builds `librentropic-inference-cuda.so` etc.) was not verified against the doc's build-matrix table — root-level build files are outside the index's parseable grammar set.
