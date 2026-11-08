## How the dependency is brought in

llama.cpp is a **vendored git submodule**, built from source in-tree. It is not a FetchContent dependency like spdlog, ryml, json, or httplib.

- **Source:** `.gitmodules` maps `extern/llama.cpp` to `ggml-org/llama.cpp`. The checked-out commit is `20a04b22`.
- **Build:** `extern/CMakeLists.txt` calls `add_subdirectory(llama.cpp EXCLUDE_FROM_ALL)`, then adds `llama.cpp/tools/mtmd` for multimodal support. It sets `LLAMA_BUILD_COMMON=ON` and `LLAMA_BUILD_TOOLS=OFF`, and it switches on `GGML_CUDA` when `ENTROPIC_HAS_CUDA` is set. Tests, examples, and the server are off.
- **Absorption:** the facade (`src/facade/CMakeLists.txt`) links `llama`, `mtmd`, and `llama-common` as `PRIVATE` with `LINK_ONLY`. They end up statically inside `librentropic.so`, and consumers never link llama directly.
- **Stale comments:** `extern/CMakeLists.txt` still says "NOT built in v1.8.0" and "Pinned at b8420". Both contradict the current build and the recorded pin bump, so they should be fixed.

## How far it reaches into entropic's source

```
 public C ABI (entropic.h)    ── no llama types (doc mentions only)
 public C++ headers           ── forward-declare llama_model / llama_context /
 include/entropic/inference/     llama_adapter_lora; raw pointers in signatures
 interfaces/i_inference_backend.h, backend.h ── abstract, no llama
 ─────────────────────────────────────────────────────────────
 src/inference/                ── concrete llama.h / common / mtmd usage
   llama_cpp_backend, _sampler, _tokenizer, orchestrator, adapter_manager,
   speculative_compat, grammar_registry, inference_c_api, interface_factory
 src/facade/entropic.cpp       ── includes llama_cpp_backend.h; dynamic_casts to
                                  LlamaCppBackend for LoRA adapter ops
 src/core, src/config, src/mcp, src/storage, src/types
                               ── no llama includes (comments and config keys only)
 python/                       ── wrapper generated from entropic.h; no llama
```

- **Confined to `src/inference/`** for the actual API calls. Every file that includes `llama.h`, `chat.h`, `sampling.h`, `speculative.h`, or `mtmd.h` is in that directory or the facade.
- **Leaks upward in three places:**
  1. `src/facade/entropic.cpp` includes the concrete backend header and downcasts to `LlamaCppBackend` at about lines 2922, 2964, and 2996. That skips the interface layer, which your architecture doc says layers should not do.
  2. `orchestrator.cpp:82` constructs `std::make_shared<LlamaCppBackend>()` directly rather than going through `interface_factory`.
  3. The public `include/entropic/inference/*.h` headers (orchestrator, adapter_manager, sampler, speculative_compat) name llama structs and pass `llama_context*` and `llama_model*` through their signatures. They do not include `llama.h`, so this is a type-name leak, not a link dependency.
- **Core, config, MCP, storage, and types** never include llama. `src/config/loader.cpp` only reads llama.cpp-named knobs such as `llama_log_path`.
- **Tests** include llama headers directly and link `llama` for vocab-only and real-model paths.

Scope note: I checked includes by grep and read the relevant CMake files. I did not build the project, so the link behaviour is from the CMake source, not a verified link.