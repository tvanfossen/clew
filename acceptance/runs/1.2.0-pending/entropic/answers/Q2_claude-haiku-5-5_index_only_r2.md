**Short answer:** llama.cpp is a git submodule under `extern/`, built into the inference library, and it is used only inside `src/inference/`. The engine's public and interface layers never see llama.cpp types. The index can't show `#include` or link lines directly, so the build wiring below comes from CMake and architecture docs, not from parsed edges.

**How it's brought in**

- `extern/llama.cpp` is a submodule. `extern/CMakeLists.txt` says it is fetched and pinned, and its comment says it is "NOT built in v1.8.0." That comment is stale: release notes say the pin moved to b9592 in v2.9.0, so treat it as history.
- `src/inference/CMakeLists.txt` says the inference library links llama.cpp, nlohmann/json and spdlog.
- `docs/architecture-cpp.md` lists `librentropic-inference-{cuda,vulkan,cpu}.so` as linking `llama.cpp` and implementing `IInferenceBackend`. So the backend is a compile-time variant (CUDA, Vulkan or CPU), which matches the design rules in `.claude/CLAUDE.md`.
- `llama_cpp_backend.cpp` header comment says it is pinned to llama.cpp submodule b8420. That also looks stale against the v2.9.0 bump.

**Where it reaches in entropic's own source**

| Layer | Llama.cpp contact |
|---|---|
| `include/entropic/inference/` (`backend.h`, `sampler.h`, `tokenizer.h`) | Abstract seams. Per the design rules, no third-party headers in interface contracts. I did not open these headers to confirm that. |
| `src/inference/llama_cpp_backend.{h,cpp}` | `LlamaCppBackend`, which is the concrete llama.cpp implementation. It owns `llama_model`, `llama_context`, the mtmd context and the vocab. It also calls the vendored `common_chat_*` and `common_speculative_*` helpers, the MTP head and speculative decode, and the state save/restore calls. |
| `src/inference/llama_cpp_sampler.{h,cpp}` | `LlamaCppSampler` and `LlamaCppSamplerFactory`, which wrap a `llama_sampler` chain. |
| `src/inference/llama_cpp_tokenizer.{h,cpp}` | `LlamaCppTokenizer`, which forwards to `llama_tokenize` and `llama_token_to_piece` and borrows the vocab. |
| `src/inference/image_preprocessor.cpp` | Uses stb_image, which is vendored with llama.cpp. |
| `include/entropic/inference/inference_c_api.cpp` | `entropic_create_inference_backend`, the factory that returns the abstract backend across the C boundary. |
| Tests | `adapter_manager_test.cpp` mocks the llama LoRA functions by link-time substitution, so llama.cpp does not need to be linked for that test. |

**Key points**

- The reach is wide inside `src/inference/`, which is roughly 135 symbols in the backend header alone, and it stops there. The C API hides llama types behind an opaque handle, as the design rules require.
- `LlamaCppBackend` exposes `llama_model_ptr()` and `llama_context_ptr()` as public methods. These are internal to the inference `.so`, not part of the C ABI.
- The index has no callers of `LlamaCppBackend` outside `src/inference/`. I could not confirm which engine-level code selects it, beyond the factory.

**Not settled by the index:** the exact `target_link_libraries` and `#include` lines, the current pin, and whether any other module includes llama headers directly. Checking `src/inference/CMakeLists.txt`, `extern/CMakeLists.txt` and `.gitmodules` would settle them.