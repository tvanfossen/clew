# Q9 — src — haiku — run 1

## Overview

**What it does:** Entropic is a **local-first agentic inference engine** (`src/cli/main.cpp:1`) that runs GGUF models on your hardware without cloud APIs. It implements the full agentic loop: generate text → parse tool calls → execute → regenerate. It's written in pure C++ with a C API facade for language independence (`include/entropic/entropic.h`).

**Key purpose:** Turn a local model into a multi-tier, tool-calling AI system with identity-based delegation, grammar-constrained output, constitutional validation, and MCP tool support — all fully local and privacy-respecting (`README.md:7-35`).

---

## Execution Entry Points

### 1. **CLI Entry** — `src/cli/main.cpp`
Three subcommands:
- `entropic mcp-bridge` — Relay stdio↔unix-socket for external MCP clients (Claude Code, VSCode) to use the engine as a tool provider (`src/cli/main.cpp:9-20, 42-96`)
- `entropic version` — Print engine version
- `entropic download` — Fetch bundled GGUF models

The bridge is the primary integration path; it connects to a running engine without starting one (`src/cli/main.cpp:10-20`).

### 2. **C API Entry** — `include/entropic/entropic.h`
Public C interface for all consumers. Lifecycle: `entropic_create()` → `entropic_configure_dir()` → `entropic_run_streaming()` → `entropic_destroy()`. Five run variants:
- `entropic_run()` — Non-streaming single prompt
- `entropic_run_streaming()` — Streaming with token callback
- `entropic_run_messages()` — Multi-message input (multimodal-ready)
- `entropic_run_as()` — Force a specific tier
- `entropic_run_batch()` — Multiple prompts in sequence

### 3. **C++ Engine Core** — `src/core/engine.cpp`, `include/entropic/core/engine.h`
**`AgentEngine::run(messages)`** is the agentic loop. State machine: `IDLE` → `PLANNING` (generate) → `EXECUTING` (tool calls) → `VERIFYING` (constitutional validation) → `COMPLETE` (`src/core/engine.cpp:1-25`). Owns response generation, context management, compaction, delegation, and hooks.

### 4. **Examples**
- **C**: `examples/headless/main.c` — Scripted conversation for CI validation
- **C++**: `examples/pychess/main.cpp` — Multi-tier chess with grammar constraints and external MCP
- **C++**: `examples/explorer/main.cpp` — Interactive REPL with delegation
- **C++**: `examples/openai-server/src/main.cpp` — OpenAI-compatible HTTP gateway

### 5. **Python Wrapper** — `python/src/entropic/__init__.py`
Thin ctypes binding (lazy-loaded). No OOP wrapper; exports the C ABI directly. Usage: `from entropic import entropic_create, entropic_configure_dir, entropic_run_streaming`.

---

## Major Subsystems

### **Core Engine** (`src/core/`, 200+ KB)
- **`engine.cpp`** (`include/entropic/core/engine.h`) — Agentic loop state machine, iteration budgets, metrics
- **`response_generator.cpp`** — Generation with prompt caching, GBNF grammar constraints, streaming
- **`context_manager.cpp`** — Message assembly, anchor tokens, compaction triggers
- **`delegation.cpp`** (`include/entropic/core/delegation.h`) — Multi-tier child execution (delegate, pipeline, complete directives)
- **`constitutional_validator.cpp`** — Critique-revise loop on generated content
- **`hook_registry.cpp`** — 20+ extensibility points (ON_LOOP_START, PRE_GENERATE, POST_TOOL_CALL, etc.)
- **`compaction.cpp`** — Context token-budget management and summarization
- **`engine_types.cpp`** — Message structs, AgentState enum, LoopMetrics

### **Inference Backends** (`src/inference/`, 150+ KB)
- **`llama_cpp_backend.cpp`** (`include/entropic/inference/backend.h`) — CUDA/Vulkan/CPU selection
- **`adapter_manager.cpp`** — Qwen3.5, generic chat adapters; LoRA hot-swap
- **`grammar_registry.cpp`** — GBNF constraint application per-tier
- **`interface_factory.cpp`** — Backend selection at startup
- **`image_preprocessor.cpp`** — Multimodal vision support hooks
- **VRAM lifecycle**: state machine (COLD/WARM/ACTIVE) with explicit load/activate/unload (`src/inference/llama_cpp_backend.cpp`)

### **MCP (Model Context Protocol)** (`src/mcp/`, 300+ KB)
- **`tool_executor.cpp`** — Dispatch tool calls, check schema, handle duplicates, apply size caps
- **`server_manager.cpp`** — Plugin `.so` loading and dispatch
- **`mcp/servers/`** — Six built-in servers:
  - **`entropic_server.cpp`** — delegate, pipeline, complete, diagnose, inspect (the engine's own tools)
  - **`filesystem.cpp`** — read_file, write_file, edit_file, glob, grep (with path traversal protection)
  - **`bash.cpp`** — execute (subprocess safety)
  - **`git.cpp`** — status, diff, log, commit, branch, checkout
  - **`diagnostics.cpp`** — diagnostics, check_errors
  - **`web.cpp`** — web_fetch, web_search (opt-in via config)
- **`external_client.cpp`** — Stdio + SSE transport for external MCP servers
- **`permission_manager.cpp`** — Per-tool authorization, persist across sessions
- **`transport_stdio.cpp`, `transport_sse.cpp`** — Pluggable transport layer
- **`tool_call_history.cpp`** — Ring buffer for diagnostics and validator prompts
- **`mcp_authorization.cpp`** — Key-set per-tool permission granularity

### **Storage & Persistence** (`src/storage/`, 50 KB)
- **`database.cpp`** (`include/entropic/storage/database.h`) — SQLite backend, parent/child conversation linkage
- **`audit_logger.cpp`** — Structured audit log of tool calls, permissions, identity transitions
- **`permission_persister.cpp`** — Remember allow/deny decisions across sessions
- **`session_logger.cpp`** — Streaming `session.log` (engine ops) + `session_model.log` (full transcripts)

### **Configuration** (`src/config/`, 50 KB)
- **`loader.cpp`** (`include/entropic/config/loader.h`) — Layered YAML/JSON resolution (compiled defaults → bundled → global → project local → environment)
- **`validate.cpp`** — Cross-field validation (routing refs, tier consistency, thresholds)
- **`bundled_models.cpp`** (`data/bundled_models.yaml`) — Registry of pre-vetted GGUF models (primary, mid, lightweight)
- **`data_dir.cpp`** — Compile-time DATA_DIR override for bundled prompts/data

### **Type Definitions** (`src/types/`, `include/entropic/types/`)
- **`message.h`**, **`tool_call.h`** — Message + ToolCall + ToolResult structs (role, content, metadata, tool_calls)
- **`config.h`** — ModelConfig, TierConfig, LoopConfig, CompactionConfig
- **`engine_types.h`** — AgentState enum, LoopMetrics, LoopContext
- **`error.h`** — entropic_error_t enum + callback types
- **`hooks.h`** — Hook point enum, callback function pointer types
- **`validation.h`** — ValidationVerdict enum, Violation structs

### **Prompts & Identity** (`src/prompts/`, 20 KB)
- **`manager.cpp`** — Per-identity prompt loading, frontmatter parsing (allowed_tools, validation_rules, relay settings, max_iterations, max_tool_calls_per_turn)
- **`classification.cpp`** — Identity detection from context

### **Facade (C API Gateway)** (`src/facade/`, 100 KB)
- **`entropic.cpp`** (`include/entropic/entropic.h`) — All public C functions (create, configure, run, run_streaming, run_messages, hooks, adapters, metrics)
- **`entropic_mcp.cpp`** — Tool registration, permission queries
- **`entropic_identity.cpp`** — Tier listing, prompt inspection
- **`entropic_compaction.cpp`** — Compaction trigger and strategy registration
- **`entropic_audit.cpp`** — Audit log access
- **`entropic_hooks.cpp`** — Hook registration/deregistration
- Wraps all subsystems with error handling; pure C at boundary

---

## Architecture Patterns

**Library Decomposition** (`docs/architecture-cpp.md:24-43`):
- **librentropic-types.so** — Shared types (zero logic)
- **librentropic-core.so** — Engine loop, state machine, context
- **librentropic-inference-{cuda,vulkan,cpu}.so** — Backend variants
- **librentropic-mcp.so** — Tool registry, executor, permission
- **librentropic-mcp-{filesystem,bash,git,…}.so** — Plugin servers
- **librentropic-storage.so** — SQLite, audit, session logs
- **librentropic-config.so** — YAML loader, identity, validation
- **librentropic.so** — Facade linking all

**No C++ ABI crossing:** Every `.so` boundary uses pure C function pointers and opaque handles. Plugin versioning via `entropic_plugin_api_version()`. Symbol visibility: hidden by default, ENTROPIC_EXPORT opts in (`docs/architecture-cpp.md:195-206`).

**Plugin Architecture:** External MCP servers load via `dlopen` at runtime (`src/mcp/server_manager.cpp`). Stdio or SSE transport. Reconnect policy + health monitoring.

---

## Testing & Quality

**Test structure:**
- **Unit tests** (Catch2 BDD) in `tests/unit/{types,core,mcp,inference,config,storage}/`
- **Model tests** (GPU) in `tests/model/` — validation against real GGUF models
- **Distribution smoke test** in `tests/distribution-smoke-consumer/` — `find_package(entropic)` consumer workflow
- **Examples** each stand as a smoke test

**Pre-commit gates** (`.pre-commit-config.yaml`):
- ruff (linter) + ruff-format (formatter)
- flake8 (style)
- knots (cognitive complexity ≤15, McCabe ≤15, nesting ≤4)
- doxygen-guard (every function has `@brief`, `@version` bumped on change)
- build + unit tests (CPU)
- per-library coverage via gcovr

**Documentation:** Every function carries doxygen comment (`@brief`, `@param`, `@return`, `@version`); version increments on body change (doxygen-guard enforces it pre-commit).

---

## Coverage Assessment

| Aspect | Scope |
|--------|-------|
| **Files indexed** | 201 (cpp + h, excluding extern/, build/, tests/) |
| **Lines of code** | ~70,000 (src + include) |
| **Subsystems** | 7 core + 6 MCP servers + 1 facade = **14** major components |
| **Public API** | Fully documented in `include/entropic/entropic.h` + README.md feature inventory |
| **Test coverage** | Unit + model + smoke tests; pre-commit gates all paths |
| **Architecture clarity** | Well-factored by subsystem; dependencies flow one direction only |

**What I traced:**
- ✅ Entry points: CLI, C API, C++ engine core, examples, Python wrapper
- ✅ Subsystem decomposition: core, inference, MCP, storage, config, types, prompts, facade
- ✅ Plugin architecture: server loading, transport, external MCP clients
- ✅ State machine: AgentEngine loop with IDLE→PLANNING→EXECUTING→COMPLETE
- ✅ Configuration: layered resolution with identity/constitution frontmatter
- ✅ Testing: unit + model + examples as smoke tests
- ✅ Pre-commit quality gates: 16 hooks

**What I did NOT fully trace** (gaps):
- Detailed algorithm flow inside **`response_generator.cpp`** (KV-cache prefix save/load, prompt injections, stream filtering) — I saw the interfaces but not the full streaming token-by-token mechanics
- **`constitutional_validator.cpp`** critique-revise loop — identified the hook points but not the retry heuristics or violation payload assembly
- **`compaction.cpp`** token-budget mechanics — saw the triggers but not the summarization strategy composition
- **MCP protocol details** — identified tools but not the full JSON-RPC 2.0 request/response envelope  
- **Grammar constraint application** — saw `grammar_registry.cpp` but not the GBNF compilation or constraint enforcement in llama.cpp
- **Python ctypes binding details** — saw the facade but not the type mapping code

---

**Tomorrow's change roadmap:** If you're making a change here tomorrow, start in `src/core/engine.cpp` (the loop), then drill into the subsystem's `.cpp` file by domain (if it's inference, go to `src/inference/llama_cpp_backend.cpp`; if it's tools, go to `src/mcp/tool_executor.cpp`). Follow the call chain via the header file in `include/entropic/{core,inference,mcp,config}/`. Check `src/facade/entropic.cpp` to see how the C API routes to your target. Pre-commit gates (`doxygen-guard`, `knots`, unit tests) will catch mistakes before commit.
