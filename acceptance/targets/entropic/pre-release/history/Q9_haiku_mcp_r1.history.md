# Q9 — mcp — haiku — run 1

> Machine-generated narrative of one benchmark cell. The authoritative record is the
> sibling `.transcript.jsonl`; this document exists so a reviewer can follow what the
> agent did without parsing JSON. If the two disagree, the JSONL is correct.

**Reasoning.** I'll start by querying the index to understand this repository's structure and purpose, then identify entry points and major subsystems.

### 1. `mcp__doxyguard-db__index`
- **asked:** action, target
- **got ⚠ error:** Error executing tool index: index(action='status') does not take a target, and '~/ddb-targets/entropic' was supplied. Refusing rather than ignoring it, because this action reports on the DERIVED target and on where that …

### 2. `mcp__doxyguard-db__search`
- **asked:** limit, target, text
### 3. `mcp__doxyguard-db__search`
- **asked:** corpus, target, text
- **got:** {"kind":"matching symbols","count":0,"results":[],"subject":"main entry point startup initialization","note":"No matching symbols for 'main entry point startup initialization'. This is NOT an error and NOT a malformed ca…

- **got:** {"directories":[{"directory":"extern","indexed_files":1237,"symbols":30077,"external_files":49705,"unresolved_files":0},{"directory":".","indexed_files":418,"symbols":43,"external_files":0,"unresolved_files":413},{"direc…

### 4. `mcp__doxyguard-db__search`
- **asked:** corpus, limit, target, text
- **got:** {"kind":"matching symbols","count":10,"results":[{"name":"main","kind":"function","file":"extern/llama.cpp/tools/parser/template-analysis.cpp","also_in":["extern/llama.cpp/tests/test-chat.cpp","extern/llama.cpp/tests/tes…

### 5. `mcp__doxyguard-db__search`
- **asked:** corpus, limit, target, text
### 6. `mcp__doxyguard-db__search`
- **asked:** corpus, target, text
- **got:** {"kind":"prose matches","count":5,"results":[{"file_path":"docs/dist-README.md","heading":"Manual tarball","snippet":"```"},{"file_path":"README.md","heading":"CUDA build (default)","snippet":"inv build --clean"},{"file_…

- **got:** {"kind":"indexed files","count":92,"results":[{"path":"src/cli/download.cpp","symbol_count":19},{"path":"src/cli/main.cpp","symbol_count":7},{"path":"src/cli/mcp_bridge.cpp","symbol_count":8},{"path":"src/cli/version.cpp…

### 7. `mcp__doxyguard-db__dossier`
- **asked:** max_neighbors, subject, target
- **got:** {"kind":"dossiers","count":3,"found":1,"subject":["entropic_create","Engine","entropic_run_request"],"results":[{"subject":"entropic_create","subject_kind":"function","name":"entropic_create","rowid":52599,"signature":"e…

### 8. `mcp__doxyguard-db__dossier`
- **asked:** max_neighbors, subject, target
- **got:** {"subject":"entropic_configure","subject_kind":"function","name":"entropic_configure","rowid":52624,"signature":"entropic_error_t entropic_configure(entropic_handle_t handle, const char *config_json)","file":"src/facade/…

### 9. `mcp__doxyguard-db__search`
- **asked:** corpus, limit, target, text
### 10. `mcp__doxyguard-db__dossier`
- **asked:** max_neighbors, subject, target
- **got:** {"kind":"matching symbols","count":0,"results":[],"subject":"entropic_run chat request response","note":"No matching symbols for 'entropic_run chat request response'. This is NOT an error and NOT a malformed call, and it…

- **got:** {"subject":"entropic_engine","subject_kind":"class","name":"entropic_engine","kind":"struct","file":"src/facade/engine_handle.h","line":73,"brief":"Engine handle struct — owns all subsystems.","members":[{"name":"hook_re…

### 11. `mcp__doxyguard-db__search`
- **asked:** corpus, limit, target, text
- **got:** {"kind":"matching symbols","count":10,"results":[{"name":"entropic_run","kind":"function","file":"include/entropic/entropic.h","brief":"Synchronous agentic loop."},{"name":"entropic_run","kind":"variable","file":"python/…

### 12. `mcp__doxyguard-db__dossier`
- **asked:** max_neighbors, subject, target
- **got:** {"subject":"AgentEngine","subject_kind":"function","name":"AgentEngine","rowid":891,"signature":"entropic::AgentEngine::AgentEngine(const InferenceInterface &inference, const LoopConfig &loop_config, const CompactionConf…

### 13. `Read`
- **asked:** file_path=~/ddb-targets/entropic/README.md
- **got:** 1	# Entropic 2	 3	> Local-first agentic inference engine — your models, your hardware, your control 4	 5	**API reference:** [tvanfossen.github.io/entropic](https://tvanfossen.github.io/entropic/) — auto-generated from do…

### 14. `mcp__doxyguard-db__dossier`
- **asked:** max_neighbors, subject, target
- **got:** {"subject":"entropic_run","subject_kind":"function","name":"entropic_run","rowid":52633,"signature":"entropic_error_t entropic_run(entropic_handle_t handle, const char *input, char **result_json)","file":"src/facade/entr…

### 15. `mcp__doxyguard-db__search`
- **asked:** corpus, limit, target, text
- **got:** {"kind":"matching symbols","count":0,"results":[],"subject":"MCP ServerManager tool executor","note":"No matching symbols for 'MCP ServerManager tool executor'. This is NOT an error and NOT a malformed call, and it is NO…

### 16. `mcp__doxyguard-db__dossier`
- **asked:** max_neighbors, subject, target
- **got:** {"kind":"dossiers","count":3,"found":2,"subject":["ModelOrchestrator","InferenceInterface","SqliteStorageBackend"],"results":[{"subject":"ModelOrchestrator","subject_kind":"class","name":"entropic::ModelOrchestrator","ki…

### 17. `mcp__doxyguard-db__search`
- **asked:** corpus, limit, target, text
### 18. `mcp__doxyguard-db__dossier`
- **asked:** max_body_lines, subject, target
- **got:** {"kind":"matching symbols","count":8,"results":[{"name":"src/inference/llama_cpp_backend.h","kind":"file","file":"src/inference/llama_cpp_backend.h","brief":"@file llama_cpp_backend.h @brief LlamaCppBackend — llama.cpp C…

- **got:** {"subject":"main","subject_kind":"function","name":"main","rowid":1154,"signature":"int main(int argc, char **argv)","file":"extern/llama.cpp/tools/parser/template-analysis.cpp","line_start":582,"line_end":611,"brief":"C…

### 19. `mcp__doxyguard-db__dossier`
- **asked:** max_body_lines, qualified, subject, target
- **got:** {"kind":"dossier","subject":"main","found":false,"note":"No dossier for 'main' in this index. This is a definitive negative from the database, NOT an error and NOT a malformed call. Before concluding the symbol does not …

### 20. `mcp__doxyguard-db__search`
- **asked:** corpus, limit, target, text
- **got:** {"kind":"prose matches","count":10,"results":[{"file_path":"docs/dist-README.md","heading":"Strip the leading `entropic/` to lay out under the prefix directly:","snippet":"tar -xzf entropic-<version>-linux-x86_64-<backen…

### 21. `Read`
- **asked:** file_path=~/ddb-targets/entropic/docs/architecture-cpp.md
- **got:** 1	# Entropic — C++ Architecture Design 2	 3	Reference architecture for the C++ engine. This document defines the 4	library decomposition, dependency graph, interface contracts, class 5	hierarchy patterns, plugin architec…

### 22. `Read`
- **asked:** file_path=~/ddb-targets/entropic/docs/architecture-cpp.md
- **got:** 200	```cpp 201	#if defined(_WIN32) 202	  #define ENTROPIC_EXPORT __declspec(dllexport) 203	#else 204	  #define ENTROPIC_EXPORT __attribute__((visibility("default"))) 205	#endif 206	``` 207	 208	Applied only to: 209	- Fac…

### 23. `mcp__doxyguard-db__search`
- **asked:** corpus, limit, target, text
- **got:** {"kind":"matching symbols","count":0,"results":[],"subject":"run_turn run_request conversation message","note":"No matching symbols for 'run_turn run_request conversation message'. This is NOT an error and NOT a malforme…

### 24. `mcp__doxyguard-db__dossier`
- **asked:** max_neighbors, subject, target
- **got:** {"subject":"run_turn","subject_kind":"function","name":"run_turn","rowid":9837,"signature":"TurnResult anonymous_namespace{test_gh108_agentic_benchmark.cpp}::run_turn(ModelOrchestrator &orch, std::vector< entropic::Messa…

### 25. `mcp__doxyguard-db__search`
- **asked:** corpus, limit, target, text
- **got:** {"kind":"matching symbols","count":0,"results":[],"subject":"coverage metrics first-party indexed","note":"No matching symbols for 'coverage metrics first-party indexed'. This is NOT an error and NOT a malformed call, an…

**Reasoning.** Based on my analysis of the index and source, here is the orientation you would need to make changes to this codebase:

## What It Does

**Entropic** is a **local-first agentic inference engine** — a C library that turns a local GGUF model into a multi-tier, tool-calling AI system. It runs entirely on your hardware with zero cloud calls or telemetry. You control the model, prompts, tools, and data. `README.md:3-19`

The engine solves the gap between a raw language model and a usable AI agent by handling:
- **Agentic loops**: generate → parse tool calls → execute → re-generate
- **Multi-tier ro

---

## Final answer as submitted

Based on my analysis of the index and source, here is the orientation you would need to make changes to this codebase:

## What It Does

**Entropic** is a **local-first agentic inference engine** — a C library that turns a local GGUF model into a multi-tier, tool-calling AI system. It runs entirely on your hardware with zero cloud calls or telemetry. You control the model, prompts, tools, and data. `README.md:3-19`

The engine solves the gap between a raw language model and a usable AI agent by handling:
- **Agentic loops**: generate → parse tool calls → execute → re-generate
- **Multi-tier routing**: same model serves different roles with different prompts and constraints
- **Context management**: auto-compaction to stay within model windows
- **Grammar constraints**: GBNF grammars force structured output
- **Local tool servers**: filesystem, bash, git, web — all MCP-based, plugin architecture
- **Privacy**: zero network calls, everything on-device

## Execution Flow

Entry point in `src/cli/main.cpp` — a CLI dispatcher. Programmatic entry starts here:

1. **`entropic_create(handle)`** `src/facade/entropic.cpp:241-266` — allocates engine, initializes logging and state
2. **`entropic_configure(handle, config_json)`** `src/facade/entropic.cpp:1749-1759` — wires up all subsystems from YAML config
3. **`entropic_run(handle, input, result_json)`** `src/facade/entropic.cpp:1974-2014` — synchronous agentic loop: appends user input to conversation, runs `engine->run_turn(input)` to completion, returns JSON

The core loop lives in `AgentEngine::run_turn()` `include/entropic/core/engine.h:2826,2988` — this is the single-turn dispatcher that orchestrates the agentic behavior.

## Major Subsystems

The engine is decomposed into independent `.so` libraries with explicit C interfaces. This structure is documented in `docs/architecture-cpp.md:17-123`. The handle `entropic_engine` owns all subsystems:

| Subsystem | Role | Key Files |
|-----------|------|-----------|
| **Core Engine** | Agentic loop, state machine, context routing | `src/core/engine.cpp`, `include/entropic/core/engine.h` — 1,105 symbols |
| **Inference** | Model loading, generation, token sampling via llama.cpp | `src/inference/llama_cpp_backend.cpp`, `ModelOrchestrator` (156 members) — manages multi-tier model lifecycle, routing, grammar constraints |
| **MCP Servers** | Tool registry and executor (filesystem, bash, git, web) | `src/mcp/server_manager.cpp`, `src/mcp/tool_executor.cpp` — loads plugins at runtime, serializes tool results as directives back to engine |
| **Configuration** | YAML loader, identity/constitution system, bundled models | `src/config/loader.cpp`, `ParsedConfig` — multi-layer config resolution (CLI, YAML, defaults) |
| **Storage** | SQLite audit log, conversation persistence, session logs | `SqliteStorageBackend` `include/entropic/storage/backend.h:188` — stores messages, tool calls, metrics |
| **Type System** | Universal message, tool call, directive, generation result types | `include/entropic/types/` — pure C types at `.so` boundaries |
| **Facade** | Unified C API wrapping all subsystems | `src/facade/entropic.cpp`, `include/entropic/entropic.h` — 149 symbols in main facade |

### Core Data Structures

**`entropic_engine`** `src/facade/engine_handle.h:73` owns:
- `orchestrator` (ModelOrchestrator) — coordinates inference
- `engine` (AgentEngine) — runs the agentic loop
- `server_manager` + `tool_executor` — manages MCP tools
- `config` (ParsedConfig) — configuration
- `storage` (SqliteStorageBackend) — audit/persistence
- `validator` (ConstitutionalValidator) — constitutional AI layer
- `compactor_registry` — context compaction strategies
- `identity_manager` — role-based context separation

**Message flow**:
1. User input → appended to conversation history
2. `AgentEngine::run_turn()` processes through:
   - Generation via ModelOrchestrator
   - Tool call parsing
   - Tool execution via ServerManager → result as directive
   - Context compaction if needed
   - Constitutional validation (critique loop)
3. Result: updated message history + metadata (tokens, finish_reason, tool calls)

## Coverage

The index covers **2,132 indexed files** across the repo:
- **src/**: 112 files (main engine code)
- **include/**: 89 files (headers)
- **tests/**: 218 files (unit + integration)
- **examples/**: 24 files (C++, C, Python samples)
- **extern/**: 1,237 files (vendored llama.cpp submodule)

**First-party codebase** (what you'd modify): ~500 files in src/ + include/ + tests/ + examples/. The submodule is self-contained and rarely touched.

## Gaps

I could not locate the CLI `main()` function in src/cli/main.cpp using the index — the index shows the file exists but did not return its dossier. This is a known gap where module-private or file-local functions may not resolve. The file documentation confirms it is a "subcommand dispatcher" but I don't have the exact dispatch logic from the index.

---

**In summary**: This is a sophisticated inference engine with clean library boundaries, multi-tier routing, tool execution, and persistent audit logs. To make changes, you'd identify which subsystem (core loop, config, inference, MCP, storage) needs modification and follow its explicit interface contract in `include/entropic/interfaces/`.
