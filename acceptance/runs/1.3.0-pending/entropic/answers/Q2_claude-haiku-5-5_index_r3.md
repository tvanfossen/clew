**How it's brought in:** llama.cpp is a git submodule at `extern/llama.cpp`, pinned to commit `20a04b22` (`.gitmodules`, gitlink in `git ls-files`). It is not a FetchContent dependency like spdlog, ryml, nlohmann/json, or httplib. `extern/CMakeLists.txt` builds it statically with `add_subdirectory(llama.cpp EXCLUDE_FROM_ALL)`. It turns on `LLAMA_BUILD_COMMON` and turns off tools, examples, server, and tests. It also adds `llama.cpp/tools/mtmd` for multimodal. `ENTROPIC_HAS_CUDA` is mapped to `GGML_CUDA`.

**Two things to check in this checkout:**
- `extern/llama.cpp` is an empty directory here, and `git submodule status` shows `-` (not initialized). Configure will fail until `git submodule update --init` runs. I did not run configure, so this is from reading the files.
- Comments disagree with the pin. `extern/CMakeLists.txt` says "pinned at b8420" and "NOT built in v1.8.0". `speculative_compat.h` cites `253ba110b`. The gitlink says `20a04b22`. The comments are stale.

**How the link flows:**

```
extern/llama.cpp (static)  ── llama, llama-common, mtmd
        │
src/inference  (OBJECT lib)   PRIVATE: llama, mtmd
        │                     PUBLIC:  llama-common
        ▼
src/facade  librentropic.so   LINK_ONLY: llama, mtmd, llama-common
                              (absorbed; consumers never link llama)
```

**How far it reaches into entropic's source:**

- **Inside `src/inference/` (the expected layer):** about nine files include `llama.h`, `chat.h`, `sampling.h`, `speculative.h` or `mtmd.h`. These are `llama_cpp_backend.{h,cpp}`, `llama_cpp_sampler`, `llama_cpp_tokenizer`, `grammar_registry`, `orchestrator`, `adapter_manager`, `speculative_compat`, and `tool_call_markers.h`. `llama_cpp_backend.h` alone has about 80 llama-touching lines. Across `src/`, 25 files reference `llama_`, `ggml_`, `mtmd_` or `common_` symbols, about 722 occurrences in total.

- **Beyond that layer (the leaks):**
  - `orchestrator.cpp` does `dynamic_cast<LlamaCppBackend*>` in about ten places. It also constructs backends directly at line 82.
  - `secondary_model_loader.cpp:47` and `inference_c_api.cpp:594` also construct `LlamaCppBackend` directly.
  - `src/facade/entropic.cpp` includes `llama_cpp_backend.h` and calls `llama_model_ptr()` and `llama_context_ptr()` for adapter load, unload and swap (around lines 2920–3001). It also calls `parse_response` for the gh#87 tool-call path.
  - `interface_factory.cpp:412` also dynamic_casts to `LlamaCppBackend`.

- **Public headers:** these don't include `llama.h`. They forward-declare `struct llama_model` and `struct llama_context` (`orchestrator.h:44-45`, `speculative_compat.h:47`) and expose raw `llama_context*` / `llama_model*` in some signatures (`orchestrator.h:759, 773, 892`; `speculative_compat.h:94`). The C API's `entropic.h` has no llama types, but its state-blob format is documented as bit-for-bit llama.cpp's `llama_state_get_data` output and not portable across llama.cpp commits (`entropic.h:928–945`). That is a format-level coupling consumers can see.

- **Clean:** `src/core`, `src/config` and `src/mcp` have no llama types. The matches there are comments or config keys such as `ggml_logging` and `llama_log_path`.

**Bottom line:** the build dependency is a pinned, statically absorbed submodule. Source-level reach stops at `src/inference/`, but the orchestrator, the facade's adapter path, and the `speculative_compat` and `orchestrator` headers reach past it. Those are the places where a llama.cpp API change would ripple into entropic's own interfaces. The architecture doc's rule that interface contracts carry no third-party headers is not fully met by the forward-declared raw pointers in `orchestrator.h` and `speculative_compat.h`.