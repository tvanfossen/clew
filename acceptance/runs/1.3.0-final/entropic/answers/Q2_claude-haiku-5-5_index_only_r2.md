**Short answer:** llama.cpp is a git submodule at `extern/llama.cpp`, compiled into the inference library. Its reach stops at `src/inference/` and the tests. The public `include/entropic/` headers show no llama types, though I could only check that at symbol level.

**How it's brought in**

- `extern/` is a git submodule. Header-only deps are INTERFACE targets fetched via FetchContent. The `extern/CMakeLists.txt` doc comment says llama.cpp is "NOT built in v1.8.0", but that is stale: the code now uses it heavily.
- `src/inference/CMakeLists.txt` links it, along with nlohmann/json and spdlog. Per `docs/architecture-cpp.md`, it goes into `librentropic-inference-{cuda,vulkan,cpu}.so`, so the backend is a compile-time variant.
- I could not see the root CMake file, which the index doesn't resolve, so I could not confirm the exact `add_subdirectory` or link line.
- The pin is inconsistent across docs. `llama_cpp_backend.cpp` says "pinned against b8420". `RELEASE_NOTES.md` (v2.9.0) records a bump to b9592 (`ac4cddeb`). `speculative_compat.h` cites a different commit. Treat the pin as unresolved until the submodule's commit is checked directly.

**How far it reaches into entropic's source**

| Layer | What touches llama.cpp |
|---|---|
| `src/inference/llama_cpp_backend.{h,cpp}` | `LlamaCppBackend`, the "15% layer" over the raw C API. Owns `llama_model*`, `llama_context*`, `llama_vocab*`, and the mtmd context. Covers decode, sampler chain, chat templates and tool-call parsing (`common_chat_*`), KV state save/restore, prompt cache, batched decode, speculative and MTP decoding. Roughly 157 members. |
| `llama_cpp_sampler.*`, `llama_cpp_tokenizer.*` | Thin adapters over `llama_sampler` chains and `llama_vocab` / `llama_tokenize`. |
| `orchestrator.cpp`, `adapter_manager.cpp` | Take `llama_model*` / `llama_context*`. Speculative pair resolution and compat checks; LoRA via `llama_adapter_lora_*`. |
| `speculative_compat.{h,cpp}` | Mirrors an upstream static check, since it is not exported from llama.cpp. Its header says it is copied from `extern/llama.cpp` `common/speculative.cpp`. This is a coupling to upstream internals that will break on pin bumps. |
| `image_preprocessor.cpp` | Uses the stb_image copy vendored with llama.cpp. |
| `include/entropic/types/config.h` | Only `llama_log_path`, a path string. |
| Tests | Unit tests substitute mock `llama_*` functions at link time (`adapter_manager_test.cpp`, `speculative_compat_test.cpp`). Model tests load GGUFs from `extern/llama.cpp/models`. |

**Boundary:** the architecture rules say no third-party headers in interface contracts and pure C at `.so` boundaries. The index supports that for `include/`. It does not show a `llama.h` include in any public header, and `llama.h` itself is not indexed. A grep of `include/` for `#include.*llama` would confirm it directly.