# Q9 — src — sonnet — run 1

> Machine-generated narrative of one benchmark cell. The authoritative record is the
> sibling `.transcript.jsonl`; this document exists so a reviewer can follow what the
> agent did without parsing JSON. If the two disagree, the JSONL is correct.

### 1. `Bash`
- **asked:** command=find ~/ddb-targets/entropic -maxdepth 2 -type d | sort
- **got:** ~/ddb-targets/entropic ~/ddb-targets/entropic/.claude ~/ddb-targets/entropic/.claude/proposals ~/ddb-targets/entropic/.claude/reports ~/ddb-targets/entropic/cmake ~/ddb-targets/entropic/data ~/ddb-targets/entropic/data/g…

### 2. `Read`
- **asked:** file_path=~/ddb-targets/entropic/README.md
- **got:** 1	# Entropic 2	 3	> Local-first agentic inference engine — your models, your hardware, your control 4	 5	**API reference:** [tvanfossen.github.io/entropic](https://tvanfossen.github.io/entropic/) — auto-generated from do…

### 3. `Bash`
- **asked:** command=cd ~/ddb-targets/entropic && echo "--- src/cli/main.cpp ---" && cat -n src/cli/main.cpp | head -80 echo "--- examples/headless/main.c ---" && cat -n examples/headless/main.c | head -60
- **got:** --- src/cli/main.cpp ---      1	// SPDX-License-Identifier: Apache-2.0      2	/**      3	 * @file main.cpp      4	 * @brief entropic CLI binary — top-level dispatcher for subcommands.      5	 *      6	 * Provides a singl…

### 4. `Bash`
- **asked:** command=ls src/core src/facade src/inference src/mcp src/storage src/config src/types src/prompts include/entropic
- **got:** include/entropic: config core entropic_config.h.in entropic_export.h entropic.h inference interfaces mcp prompts storage types  src/config: bundled_models.cpp CMakeLists.txt data_dir.cpp env_overrides.cpp loader.cpp vali…

### 5. `Bash`
- **asked:** command=sed -n '80,140p' src/cli/main.cpp echo "---entropic_create---" grep -n "entropic_create\|^int\|^entropic_error_t\|create(" src/facade/entropic.cpp | head -30 echo "---engine.cpp loop---" grep -n "^.*loop(\|^AgentState\|execute_iteration" src/core/engine.cpp | head -30
- **got:** };  /**  * @brief Adapter for `version` which takes no args.  * @internal  * @return Subcommand exit code.  * @version 2.0.5  */ int run_version_adapter(int, char*[]) {     return entropic::cli::run_version(); }  constex…

### 6. `Bash`
- **asked:** command=cat -n CMakeLists.txt | sed -n '1,60p' echo "---top-level file counts---" find src include -name "*.cpp" -o -name "*.h" -o -name "*.hpp" | wc -l find src -name "*.cpp" | wc -l find include -name "*.h" | wc -l
- **got:** 1	# SPDX-License-Identifier: Apache-2.0      2	cmake_minimum_required(VERSION 3.21)      3	      4	# v2.1.2 (#4): single source of truth. The repo-root VERSION file is the      5	# canonical project version — CMake reads…

### 7. `Read`
- **asked:** file_path=~/ddb-targets/entropic/src/core/engine.cpp
- **got:** 461	void AgentEngine::loop(LoopContext& ctx) { 462	    fire_loop_start_hook(hooks_, ctx);  // ON_LOOP_START (v1.9.1) 463	 464	    while (!should_stop(ctx)) { 465	        ctx.metrics.iterations++; 466	 467	        if (int…

### 8. `Read`
- **asked:** file_path=~/ddb-targets/entropic/src/facade/entropic.cpp
- **got:** 241	entropic_error_t entropic_create(entropic_handle_t* handle) { 242	    if (handle == nullptr) { 243	        return ENTROPIC_ERROR_INVALID_ARGUMENT; 244	    } 245	    entropic::log::init(spdlog::level::info); 246	    e…

**Reasoning.** Now I have enough to write a thorough orientation answer.

## Answer

**What it is:** Entropic is a C-ABI, C++20-implemented local inference engine that turns a GGUF model (via a vendored/submoduled `llama.cpp`, `extern/llama.cpp`) into an agentic, tool-calling AI system: generate → parse tool calls → execute → re-generate, with multi-tier "identity" delegation, grammar-constrained output, and MCP tool servers, all running with zero network calls except an opt-in `web` MCP server. This is stated directly in `README.md:9-18` and `README.md:402`.

**Where execution begins (two entry points, both

---

## Final answer as submitted

Now I have enough to write a thorough orientation answer.

## Answer

**What it is:** Entropic is a C-ABI, C++20-implemented local inference engine that turns a GGUF model (via a vendored/submoduled `llama.cpp`, `extern/llama.cpp`) into an agentic, tool-calling AI system: generate → parse tool calls → execute → re-generate, with multi-tier "identity" delegation, grammar-constrained output, and MCP tool servers, all running with zero network calls except an opt-in `web` MCP server. This is stated directly in `README.md:9-18` and `README.md:402`.

**Where execution begins (two entry points, both are library consumers, not the library's own "main"):**

1. **The `entropic` CLI binary** — `src/cli/main.cpp:110` (`int main`). It's a thin subcommand dispatcher (`mcp-bridge`, `download`, `version`) declared in a `kSubcommands` table (`src/cli/main.cpp:92-96`); it does not itself run the engine loop, it dispatches to `entropic::cli::run_mcp_bridge` etc.
2. **The actual engine lifecycle** starts from the public C API in `src/facade/entropic.cpp`: a consumer calls `entropic_create()` (`src/facade/entropic.cpp:241`) to allocate an `entropic_engine` handle and init logging, then `entropic_configure_dir()`/`entropic_configure()` to load layered YAML config, then `entropic_run_streaming()` (`src/facade/entropic.cpp:2222`) or `entropic_run()` (`src/facade/entropic.cpp:1974`) to actually drive a turn. The README's usage example (`README.md:117-136`) and the `headless` example (`examples/headless/main.c:25-53`, using `entropic_run_streaming` + a token callback) show this pattern concretely.
3. Internally, `entropic_run*` eventually calls `AgentEngine::run_loop` → `AgentEngine::loop` (`src/core/engine.cpp:461-500`), which repeatedly calls `execute_iteration` (`src/core/engine.cpp:508`) until `should_stop` or an iteration cap forces a synthetic completion (`src/core/engine.cpp:479-497`). This is the true "engine heartbeat."

**Major subsystems (by directory, `src/` has ~92 `.cpp` files, `include/entropic` ~89 headers — I did not read every file, see Gaps):**

| Subsystem | Dir | Role |
|---|---|---|
| Core engine loop | `src/core/` | `engine.cpp` (state machine IDLE→GENERATING→EXECUTING→VERIFYING→COMPLETE), `delegation.cpp`, `identity_manager.cpp`, `constitutional_validator.cpp`, `compaction.cpp`, `hook_registry.cpp`, `context_manager.cpp`, `directives.cpp`, `sandbox.cpp` |
| Facade / public C API | `src/facade/` | `entropic.cpp` (the ~20 `entropic_*` entry points), plus split-out `entropic_hooks.cpp`, `entropic_mcp.cpp`, `entropic_storage.cpp`, `entropic_identity.cpp`, `external_bridge.cpp` (the MCP bridge socket server) |
| Inference backend | `src/inference/` | `llama_cpp_backend.cpp`/`.h`, `orchestrator.cpp`, `grammar_registry.cpp` (GBNF), `adapters/` (chat template adapters), `prompt_cache.cpp`, `throughput_tracker.cpp` |
| MCP tooling | `src/mcp/` | `tool_executor.cpp`, `server_manager.cpp` (dlopen plugin loading), `servers/` (per-tool implementations: filesystem, bash, git, web, entropic, diagnostics), transports (`transport_stdio.cpp`, `transport_sse.cpp`), auth (`mcp_authorization.cpp`, `mcp_key_set.cpp`, `permission_manager.cpp`) |
| Config | `src/config/` | `loader.cpp`, `env_overrides.cpp`, `validate.cpp`, `bundled_models.cpp` — layered YAML resolution |
| Storage | `src/storage/` | `database.cpp` (SQLite), `audit_logger.cpp`, `permission_persister.cpp` |
| Prompts/identity | `src/prompts/` | `manager.cpp` (per-identity frontmatter: `allowed_tools`, `validation_rules`, etc.) |
| Types/shared | `src/types/` | `config.cpp`, `messages_json.cpp`, `session_logger.cpp`, `logging.cpp` (spdlog) |
| CLI | `src/cli/` | `main.cpp` dispatcher, `mcp_bridge.cpp`, `download.cpp` |
| Python wrapper | `python/` | thin ctypes binding (`python/src/entropic/`), no OOP layer per README |
| Examples | `examples/` | `headless` (C), `pychess`, `explorer`, `openai-server` (C++) — the fastest way to see the engine run |
| Tests | `tests/` | `unit/`, `regression/`, `integration/`, `model/`, `benchmark/`, `stress/`, `edge/`, `concurrency/`, `distribution-smoke-consumer/` — Catch2 v3 |
| Build | top-level `CMakeLists.txt` + `cmake/` | static sublibs absorbed into one `librentropic.so`; `ENTROPIC_CUDA`/`ENTROPIC_VULKAN`/`ENTROPIC_CPU_ONLY` backend options (`CMakeLists.txt:38-56`) |

**If I had to change something tomorrow**, I'd start at whichever public `entropic_*` facade function is closest to the change (`src/facade/entropic.cpp` is the seam between consumer code and everything else), trace into `src/core/engine.cpp`'s loop/state machine for behavior changes, or into `src/mcp/`/`src/inference/` for tool or model-backend changes — and I'd read an example (`examples/headless/main.c` or `examples/pychess`) first to see the intended call pattern before touching internals.

## Gaps

- I did not read every one of the ~92 `.cpp`/~89 header files; the subsystem table above is built from `README.md`'s own file-by-file feature map (cross-checked against `ls` of each `src/` subdirectory) plus direct reads of `src/cli/main.cpp`, `src/facade/entropic.cpp` (partial), `src/core/engine.cpp` (partial), and `examples/headless/main.c`. Treat the README citations in the "Features" section as README-asserted, not independently line-verified by me beyond the ones I opened.
- I did not build the project or run tests, so I can't confirm the CMake option matrix (`CMakeLists.txt:38-56`) actually wires up the way the comments describe.
- `python/`, `data/`, `docs/`, `.entropic/`, and the full `tests/` tree were only listed (`Bash find`), not read — I can't characterize their internals beyond directory names.
- I did not inspect `extern/llama.cpp` (submodule) at all — treated as an external dependency per the README's architecture diagram (`README.md:50-68`).

Estimate: this answer is grounded in direct reads of maybe 5-6 files (~a few hundred lines) plus one directory listing and the README, out of ~200+ source files — a top-level orientation, not a subsystem-by-subsystem audit.
