**Short answer:** llama.cpp comes in as a git submodule at `extern/llama.cpp`, linked by the inference library's CMake target. Its C API is used directly in one implementation family, `src/inference/llama_cpp_*`, and is reachable from the rest of the engine only through the inference-backend interface. The public headers do not expose it.

**How it's brought in (from the index, not the CMake bodies)**

- `extern/` holds the third-party code. `extern/CMakeLists.txt` says external deps are fetched at configure time, and that llama.cpp is a submodule. Its comment says it is "NOT built in v1.8.0," which is stale: later release notes describe a current pin bump.
- `src/inference/CMakeLists.txt` says the inference library "Links against llama.cpp, nlohmann/json, and spdlog." It is built per compute backend (CUDA, Vulkan, CPU), per `docs/architecture-cpp.md`.
- `RELEASE_NOTES.md` records the submodule moving to `b9592` (2026-06-11) in v2.9.0.
- Caveat: `llama_cpp_backend.cpp` still says "Pinned against llama.cpp submodule b8420," and the header mentions a `LlamaCppBackend_b8420` subclass. The index has no such symbol, so that comment looks outdated. I could not confirm the exact CMake target or include path from the index. Reading `src/inference/CMakeLists.txt` and `extern/CMakeLists.txt` would settle it.

**How far it reaches into entropic's source**

| Layer | Touches llama.cpp? | Evidence |
|---|---|---|
| `include/entropic/` (public API, interfaces) | No, as far as the index shows | The only hit is `llama_log_path` in `types/config.h`, a plain config string. No llama types appear in the public headers. |
| `src/inference/llama_cpp_backend.{h,cpp}` | Yes, deeply | `LlamaCppBackend`, ~134 members. Calls `llama_model_load_from_file`, `llama_init_from_model`, and the vocab/sampler/chat/mtmd APIs. Covers decode loop, prefix KV cache, multi-sequence batching, MTP speculative decode, and vision via mtmd. |
| `src/inference/llama_cpp_sampler.{h,cpp}` | Yes | `LlamaCppSampler` wraps a `llama_sampler*` chain. `LlamaCppSamplerFactory` builds entropic's sampler chain. |
| `src/inference/llama_cpp_tokenizer.{h,cpp}` | Yes | `LlamaCppTokenizer` forwards to `llama_tokenize` and `llama_token_to_piece` against a borrowed `llama_vocab*`. |
| `src/inference/image_preprocessor.cpp` | Indirectly | Uses stb_image vendored with llama.cpp. |
| `tests/unit/inference/*` | Mocked | Link-time mocks of `llama_*` functions, so tests run without the real library. |

**Boundary rule.** The design doc (`docs/architecture-cpp.md`) and the project rules say the llama.cpp dependency stays inside the inference `.so`. Interfaces are pure C with opaque handles, and no third-party headers appear in interface contracts. The index supports this for the public headers. It is not a full proof: the index doesn't show whether any `include/entropic/inference/*.h` header includes `llama.h`, and the search only found the `llama_log_path` config string.

**Net:** llama.cpp is a vendored submodule compiled into the per-backend inference library. Everything that calls its C API lives in the `src/inference/llama_cpp_*` files, and the rest of entropic reaches it only through the `IInferenceBackend` and `Tokenizer`/`Sampler` seams.