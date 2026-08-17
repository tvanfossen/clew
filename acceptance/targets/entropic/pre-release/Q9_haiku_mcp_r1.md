# Q9 — mcp — haiku — run 1

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
