**Short answer:** llama.cpp is a vendored git submodule, compiled from source into `librentropic.so` as a private static dependency. Its types are used inside `src/inference/` and in one place in the facade. The public C ABI does not expose them, but a few public C++ headers under `include/entropic/inference/` do.

## How it is brought in

- **Submodule:** `.gitmodules` maps `extern/llama.cpp` to `ggml-org/llama.cpp`. The `extern/CMakeLists.txt` comment says it is pinned at `b8420`.
- **Build:** `extern/CMakeLists.txt` runs `add_subdirectory(llama.cpp EXCLUDE_FROM_ALL)`, then `add_subdirectory(llama.cpp/tools/mtmd ...)` for multimodal. Upstream's tools/examples/server are switched off. `LLAMA_BUILD_COMMON=ON` is forced so the `llama-common` target exists. `ENTROPIC_HAS_CUDA` is bridged to `GGML_CUDA`.
- **Targets used:** `llama`, `llama-common` (the `common/` helpers: `chat.h`, `sampling.h`, `speculative.h`), and `mtmd`.
- **Absorbed, not exported:** `src/facade/CMakeLists.txt` links `llama`, `mtmd` and `llama-common` as `$<LINK_ONLY:>` privately into `entropic-facade`. The comment says consumers never link llama directly. `src/inference/CMakeLists.txt` links `llama` and `mtmd` PRIVATE, and `llama-common` PUBLIC, into the inference object library.
- **Include paths:** `src/inference` gets `extern/llama.cpp/{vendor,common}`. The facade gets `extern/llama.cpp/{include,ggml/include}`.

## How far into entropic's source it reaches

| Layer | Reach |
|---|---|
| `src/inference/` | Deep. `llama_cpp_backend.{h,cpp}`, `llama_cpp_sampler`, `llama_cpp_tokenizer`, `orchestrator.cpp`, `adapter_manager.cpp`, `grammar_registry.cpp`, `speculative_compat.cpp`, `secondary_model_loader.cpp`, `inference_c_api.cpp`, `interface_factory.cpp`, and the `tool_call_markers.h` / `prompt_cache.h` / `warm_keep_util.h` helpers. `LlamaCppBackend` is the only concrete backend and derives from `entropic::InferenceBackend`. |
| `src/facade/entropic.cpp` | Shallow. It `dynamic_cast`s to `LlamaCppBackend` for LoRA and adapter wiring, and calls `llama_model_ptr()` / `llama_context_ptr()`. |
| `src/core/`, `src/config/`, `src/mcp/`, `src/storage/`, `src/cli/` | None. No llama includes. `config/loader.cpp` only reads config keys (`ggml_logging`, `llama_log_path`). The core talks to the backend through the `InferenceBackend` abstraction. |
| `python/` | None. The wrapper is generated from `entropic.h`. |
| `tests/` | Direct. Many `tests/model/` and `tests/unit/inference/` files include `llama.h` or `chat.h`. |

## Where it leaks into the public surface

- **C ABI (`include/entropic/entropic.h`):** no llama types in signatures. llama.cpp appears only in doc comments, such as the state-blob portability note.
- **C++ public headers under `include/entropic/inference/`:** these forward-declare `struct llama_model`, `llama_context`, `llama_adapter_lora` and use them in method signatures:
  - `orchestrator.h`: `deactivate_if_active(llama_context*)`
  - `adapter_manager.h`: `load(..., llama_model*, ...)`, `activate(..., llama_context*)`, and `AdapterManager::handle` fields
  - `speculative_compat.h`: `check(const llama_model* target, const llama_model* draft)`

  These are opaque pointers, so consumers don't link against llama. But the headers are not llama-free, and the "no third-party headers in interface contracts" rule in `CLAUDE.md` is only partly met here.

## Things to fix or check

- **Stale comment:** `extern/CMakeLists.txt` says "llama.cpp is a submodule but NOT built in v1.8.0", which contradicts the `add_subdirectory` calls directly below it.
- **Not built here:** this is from reading the CMake and source, not from a configure or build.