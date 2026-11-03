**Short answer:** llama.cpp enters the build as a git submodule under `extern/`. Its C API is called directly from a small set of `src/inference/` files. It reaches the public `include/entropic/inference/` headers in one place, a signature that exposes `llama_model*`, so the dependency is not fully contained in the implementation layer.

**How it is brought in**

- `extern/CMakeLists.txt` says external dependencies are fetched at configure time with `FetchContent`, and that llama.cpp is a submodule. Its comment says it is "NOT built in v1.8.0". That comment is from an early version and looks stale, since later files cite a pinned submodule commit (`b8420`).
- `src/inference/CMakeLists.txt` says the inference library links against llama.cpp, nlohmann/json and spdlog. The inference library is the only target I found that links it.
- The index does not show the root `CMakeLists.txt` or the exact link line, so I cannot confirm how the submodule is built or which target exports it. Those files are indexed as unresolved, and the search did not return them.

**How far it reaches into entropic's source**

| Layer | Reach |
|---|---|
| `src/inference/llama_cpp_backend.{h,cpp}` | Deep. `LlamaCppBackend` makes direct llama.cpp C API calls (model load, context, batch decode, KV/state save and restore, MTP, multimodal, sampler chain, chat templates). Its header is about 134 symbols and documents "Direct llama.cpp C API (not llama-cpp-python wrapper)". |
| `src/inference/llama_cpp_sampler.{h,cpp}` | Wraps a `llama_sampler` chain behind the abstract `Sampler` and `SamplerFactory` interfaces. |
| `src/inference/llama_cpp_tokenizer.{h,cpp}` | Wraps `llama_tokenize` and `llama_token_to_piece` behind the abstract `Tokenizer` interface. It borrows a `llama_vocab*` owned by the model. |
| `src/inference/adapter_manager.cpp` | LoRA lifecycle via `llama_adapter_lora_init` and `llama_set_adapters_lora`. |
| `src/inference/adapters/adapter_registry.cpp` | Uses llama.cpp `common_chat` for tool-call parsing in some model families. |
| `src/inference/image_preprocessor.cpp` | Uses llama.cpp's vendored stb_image. |
| `src/inference/speculative_compat.cpp` (header in `include/entropic/inference/`) | Re-implements llama.cpp's vocab-compatibility check in entropic, because upstream's version is file-private. |
| `include/entropic/inference/orchestrator.h`, `resolve_speculative_pair` | Public header. Its signature is `ModelOrchestrator::resolve_speculative_pair(llama_model *&target_out, llama_model *&draft_out)`, so `llama_model*` appears in a public interface. |

The abstract `Sampler` and `Tokenizer` seams (`include/entropic/inference/sampler.h`, `tokenizer.h`) exist so unit tests can run without a model, and tests mock the llama.cpp symbols at link time. Tests reach llama.cpp more than the public API does, which is expected.

**Where the boundary is leaky**

The architecture rules in `.claude/CLAUDE.md` say the C interface is pure C, that no third-party headers appear in interface contracts, and that concrete base classes are the only place llama.cpp is wrapped. The `resolve_speculative_pair` signature breaks the "no third-party types in interface contracts" rule, because it hands `llama_model*` to orchestrator callers. I have not confirmed from the index whether `llama_model` is forward-declared there or pulled in by include, but the signature itself is a leak.