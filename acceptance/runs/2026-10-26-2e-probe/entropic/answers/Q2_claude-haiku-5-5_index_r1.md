**Short answer:** llama.cpp is a git submodule at `extern/llama.cpp`, compiled statically into `librentropic.so` via `add_subdirectory`. Its types are confined to the C++ inference layer and never reach the C ABI. The containment is partial, though: the facade and orchestrator call the llama C API directly in several places.

## How it's brought in

- **Submodule, not FetchContent.** `.gitmodules` points at `ggml-org/llama.cpp`, and the gitlink is `20a04b2`. spdlog, ryml, json, Catch2 and httplib are FetchContent; llama.cpp is the only one vendored as a submodule.
- **Not initialised in this checkout.** `extern/llama.cpp/` is empty and `git submodule status` shows `-20a04b2…`. A build needs `git submodule update --init` first.
- **Configured in `extern/CMakeLists.txt`:**
  - Sets `LLAMA_BUILD_TESTS/EXAMPLES/SERVER/TOOLS` off and `LLAMA_BUILD_COMMON` on.
  - Maps `ENTROPIC_HAS_CUDA` to `GGML_CUDA`.
  - Forces `BUILD_SHARED_LIBS OFF`, so it is static.
  - Runs `add_subdirectory(llama.cpp EXCLUDE_FROM_ALL)`, then adds only `llama.cpp/tools/mtmd` for multimodal.
- **Linked privately into the facade.** `src/facade/CMakeLists.txt:33-49` links `llama`, `mtmd` and `llama-common` as `LINK_ONLY` under `PRIVATE`. `src/inference/CMakeLists.txt:66-69` links the same targets for the inference library. Consumers of the installed library never link llama.

```
extern/CMakeLists.txt
  add_subdirectory(llama.cpp)          ─┐
  add_subdirectory(llama.cpp/tools/mtmd) ├─ static libs (EXCLUDE_FROM_ALL)
                                        │
src/inference  ── links llama, mtmd, llama-common
src/facade     ── absorbs them PRIVATE ──► librentropic.so  (no llama in exports)
```

## How far it reaches into entropic's source

| Layer | Reach |
|---|---|
| `include/entropic/entropic.h` (C ABI) | No llama identifiers. Clean. |
| `include/entropic/inference/*.h` (public C++) | Forward declarations `struct llama_model/llama_context/llama_adapter_lora` (`orchestrator.h:44-45`, `adapter_manager.h:37-39`, `speculative_compat.h:47`). Raw `llama_*` pointers appear in signatures (`orchestrator.h:759,773,892`, `adapter_manager.h:71-113`). No llama.h include. |
| `src/inference/llama_cpp_backend.h:33` | Includes `<llama.h>` directly. This is the chokepoint. |
| `llama_cpp_backend.cpp` | Includes `llama.h`, `common.h`, `chat.h`, `sampling.h`, `speculative.h`, `mtmd.h`, `mtmd-helper.h`. |
| Other `src/inference` files including llama headers | `llama_cpp_sampler.cpp`, `llama_cpp_tokenizer.cpp`, `speculative_compat.cpp`, `adapter_manager.cpp`, `orchestrator.cpp`, `grammar_registry.cpp`. `tool_call_markers.h` includes `chat.h` at header level. |
| Files that include the backend header | `interface_factory.cpp`, `secondary_model_loader.cpp`, `inference_c_api.cpp`, `src/facade/entropic.cpp`. |
| Direct C API calls outside the backend | `orchestrator.cpp:1287` calls `llama_memory_clear(llama_get_memory(ctx), true)`. `inference_c_api.cpp:657,709` calls `llama_log_set`. |
| Facade accessors | `src/facade/entropic.cpp:2923-3001` uses `llama_model_ptr()` and `llama_context_ptr()` for adapter wiring. |

So the design intent is that `LlamaCppBackend` is the only class touching llama.cpp, with the sampler and tokenizer split out as seams (v2.3.10). In practice the orchestrator and the facade reach past it to the raw C API.

## Tests

Several unit tests link `llama` directly. Some define mock symbols with the real llama names (for example `llama_adapter_lora_init` in `adapter_manager_test.cpp` and `llama_vocab_*` in `speculative_compat_test.cpp`). Those mocks shadow the real library at link time.

## Things I noticed

- `extern/CMakeLists.txt` still says llama.cpp is "NOT built in v1.8.0", which is stale.
- The backend header says it is pinned at `b8420`. I did not verify that against the gitlink, because the submodule is not checked out.