**How it's brought in:** llama.cpp is a git submodule at `extern/llama.cpp` (`.gitmodules`), pinned to a specific commit. The root `CMakeLists.txt:134` calls `add_subdirectory(extern)`, and `extern/CMakeLists.txt` builds it in-tree with `add_subdirectory(llama.cpp EXCLUDE_FROM_ALL)`. Before that call it forces most of llama.cpp's own options off (tests, examples, server, tools) and turns on `LLAMA_BUILD_COMMON`. It maps `ENTROPIC_HAS_CUDA` to `GGML_CUDA`. It also adds `tools/mtmd` separately for multimodal. Everything is `EXCLUDE_FROM_ALL`, and the libraries are static.

The linkage is:

```
extern/llama.cpp (submodule)
  ├─ llama, ggml        ─┐
  ├─ mtmd               ─┼─> src/inference  (PRIVATE: llama, mtmd; PUBLIC: llama-common)
  └─ llama-common       ─┘        │
                                  └─> src/facade (LINK_ONLY: llama, mtmd, llama-common)
                                        └─> librentropic.so  (absorbed statically)
```

Consumers never link llama.cpp directly.

**How far it reaches:**

| Layer | Touches llama.cpp? |
|---|---|
| `src/inference/` | Yes. This is the only real consumer. `llama_cpp_backend`, `_sampler`, `_tokenizer`, `adapter_manager`, `orchestrator`, `speculative_compat`, `grammar_registry`, `interface_factory`, `inference_c_api`, and the nemotron3 adapter all include `llama.h` or `mtmd.h`. |
| `src/facade/entropic.cpp` | Partly. It includes `llama_cpp_backend.h`, `dynamic_casts` to `LlamaCppBackend`, and calls `llama_model_ptr()` and `llama_context_ptr()` for adapter load, unload, and swap. It never includes `llama.h` itself. |
| `src/core/` | No includes. Only comments mention llama.cpp. |
| `src/config/loader.cpp` | No includes. It parses llama-related config keys (`ggml_logging`, `llama_log_path`, the ModelConfig knobs) as plain data. |
| `include/entropic/entropic.h` (C ABI) | No. Only doc comments refer to llama.cpp. |
| `include/entropic/inference/*.h`, `interfaces/i_inference_backend.h` (C++) | Forward declarations only: `struct llama_model;`, `llama_context`, `llama_adapter_lora`. Several public signatures take `llama_context*` or `llama_model*`, for example `orchestrator.h:759` and `adapter_manager.h`. |
| Tests | Heavy. Several tests include `llama.h` directly. Some mock llama.cpp symbols at link time, such as `adapter_manager_test.cpp` and `speculative_compat_test.cpp`. |

So the dependency stops at the `src/inference` layer and the facade's adapter glue. The C ABI and the core/config layers are clean. The one leak is the C++ public headers under `include/entropic/inference/`. They name llama.cpp pointer types, which is a soft break of the architecture doc's "no third-party headers in interface contracts" rule. Forward declarations don't pull in headers, so I'd call this a design smell rather than a compile problem.

**Things you should know:**

- **The submodule is not checked out here.** `git submodule status` shows `-20a04b22…` (the leading `-` means uninitialized), and `extern/llama.cpp/` is empty. Configuring would fail until you run `git submodule update --init extern/llama.cpp`. I did not run it.
- **A comment in `extern/CMakeLists.txt` is stale.** It says llama.cpp is "NOT built in v1.8.0". It has been built since v1.8.2.
- **The pin has moved.** The source comments say b8420. `docs/architecture-cpp.md` (decision 45) records a later bump to `20a04b22` (b9886). Some comments in the code still reference the older pin.