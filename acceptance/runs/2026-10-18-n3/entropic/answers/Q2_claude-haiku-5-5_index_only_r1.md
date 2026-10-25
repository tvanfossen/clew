**How it's brought in:** llama.cpp is a git submodule at `extern/llama.cpp/` (`docs/architecture-cpp.md`, Project Structure). The architecture doc lists `librentropic-inference-{cuda,vulkan,cpu}.so` as linking against `llama.cpp`, so it is a direct link, not a runtime plugin. The `.so` boundary is the one the design rules set: C interface outside, C++ inside, no C++ ABI crossing. I could not read the CMake files, so the exact link mechanics are from the docs, not the build script.

**Pin:** the pin has moved over time. `llama_cpp_backend.cpp`'s file doc says "pinned against b8420", but `RELEASE_NOTES.md` records later bumps to `b9592`, `b9886` and others. That file-doc pin is stale.

**How far it reaches into entropic's source:** it stops at `src/inference/`, and the public surface stays clean.

```
include/entropic/interfaces/   (InferenceBackend, Sampler, Tokenizer: no llama types)
        ▲ implements
src/inference/llama_cpp_*      ──► extern/llama.cpp  (llama_model_load_from_file,
  LlamaCppBackend   (derives from entropic::InferenceBackend)   llama_init_from_model,
  LlamaCppSampler   (wraps llama_sampler chain)                 llama_tokenize, mtmd, ...)
  LlamaCppTokenizer (borrows llama_vocab*)
        ▲
orchestrator: dynamic_casts to LlamaCppBackend for speculative/MTP paths
```

- **Public headers:** the only llama-related hit under `include/` is `llama_log_path`, a config field. The interface-contract rule (no third-party headers) appears to hold, though my search was capped at 40 results.
- **Implementation:** `llama_cpp_backend`, `llama_cpp_sampler` and `llama_cpp_tokenizer` (`.h`/`.cpp`) are the only files that call the llama C API. `LlamaCppBackend` is the largest of these and holds `model_`, `ctx_`, `vocab_`, and the mtmd (multimodal) context. It also uses `common_chat` and the speculative and MTP helpers from the vendored tree.
- **Vendored code beyond llama.cpp's API:** `image_preprocessor.cpp` uses `stb_image`, which is vendored with llama.cpp, so that dependency reaches one more entropic file.
- **Tests:** unit tests do not link the real llama.cpp. Several mock its C functions by link-time substitution (`adapter_manager_test.cpp`, `speculative_compat_test.cpp`, `vocab_only_smoke_test.cpp`). The real llama path is covered by model tests, which the release gates run on GPU.

**Summary:** the dependency is a git submodule linked into the three inference `.so` variants. Its API is confined to three adapter classes in `src/inference/`, which implement entropic's own interfaces, so llama.cpp does not leak into the public headers or the rest of the engine. The one caveat is that the orchestrator downcasts to `LlamaCppBackend` for speculative and MTP decoding, which couples it to that concrete class.