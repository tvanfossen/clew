**How it's brought in:** llama.cpp is a git submodule at `extern/llama.cpp` (`.gitmodules`, pinned by commit `20a04b22`), not a FetchContent download like spdlog, ryml, json, or httplib. `extern/CMakeLists.txt` runs `add_subdirectory(llama.cpp EXCLUDE_FROM_ALL)` and also adds `llama.cpp/tools/mtmd` for multimodal. It turns on `LLAMA_BUILD_COMMON` and turns off tools, tests, examples, and server. It also maps `ENTROPIC_HAS_CUDA` to `GGML_CUDA`. The targets are static: `src/facade/CMakeLists.txt` links `llama`, `mtmd`, and `llama-common` as `$<LINK_ONLY:>` PRIVATE, so they are absorbed into `librentropic.so`. Consumers never link llama directly.

**Problems I found in this checkout:**
- `extern/llama.cpp` is an empty directory. `git submodule status` shows the leading `-`, meaning it isn't initialized. A configure or build here will fail until `git submodule update --init extern/llama.cpp` is run. I did not attempt a build.
- The comment at the top of the llama section in `extern/CMakeLists.txt` says llama.cpp is "NOT built in v1.8.0." The code directly below builds it, so the comment is stale.

**How far it reaches into entropic's source:**

```
                       ┌───────────────────────────────┐
  public include/      │ no #include <llama.h>          │  C ABI (entropic.h)
  entropic/*.h         │ opaque fwd decls + 1 pointer   │  is llama-free
                       │  (speculative_compat.h)        │
                       └──────────────┬────────────────┘
                                      │
  src/inference/  ──── #include <llama.h> ──────────────► llama.cpp
    llama_cpp_backend.{h,cpp}  (+ common/chat/sampling/speculative/mtmd)
    orchestrator.cpp, adapter_manager.cpp,
    grammar_registry.cpp, speculative_compat.cpp
    tool_call_markers.h  (includes chat.h)
                                      ▲
  src/facade/entropic.cpp ── dynamic_cast<LlamaCppBackend*> ── adapter load/unload/swap
  tests/unit, tests/model ── #include <llama.h> directly (8+ files)
```

- **Confined to `src/inference/`.** That is the backend, orchestrator, adapter manager, grammar registry, and speculative-compat code. `llama_cpp_backend.cpp` also pulls in `common.h`, `chat.h`, `sampling.h`, `speculative.h`, `mtmd.h`, and `mtmd-helper.h`.
- **Public headers are mostly clean.** Nothing under `include/` includes llama. `orchestrator.h` and `speculative_compat.h` forward-declare `llama_model` and `llama_context`. `speculative_compat.h` also exposes a `const llama_model*` in a public signature, so that is the one place a llama type crosses into the public API. It is opaque, though, so it does not affect the C ABI.
- **The facade bypasses the backend interface.** `src/facade/entropic.cpp` includes `llama_cpp_backend.h` and `dynamic_cast`s to `LlamaCppBackend` to reach `llama_model_ptr()` and `llama_context_ptr()` for LoRA adapter operations. Those calls don't go through `IInferenceBackend`, so this is a seam worth flagging against the architecture's layering rule.
- **Logging hooks:** `i_inference_backend.h` exposes functions that redirect or silence llama and ggml logs, which is a deliberate leak of the dependency into the interface.
- **Python:** I found no llama references under `python/`.

Net: the dependency is built from the submodule and absorbed statically, and its headers are confined to `src/inference/`, the facade's adapter path, and tests. The C ABI remains llama-free. The main thing to fix is the facade's direct cast to the concrete backend.