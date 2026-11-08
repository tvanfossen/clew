**Short answer:** llama.cpp is a git submodule under `extern/llama.cpp`, linked into the inference library. Its types and calls stay inside `src/inference/`, with the C ABI as the outer boundary. I answered from the index only, so I could not read the CMake bodies themselves.

**How it's brought in**

- `extern/` holds llama.cpp as a git submodule. `extern/CMakeLists.txt` describes external dependencies as fetched at configure time via FetchContent, with header-only libraries as INTERFACE targets. Its comment says llama.cpp "is a submodule but NOT built in v1.8.0." That comment is from the v1.8.0 scaffold, so it is stale.
- `src/inference/CMakeLists.txt` is the consumer. Its doc says the inference library "Links against llama.cpp, nlohmann/json, and spdlog," and that the build variant depends on the compute backend.
- `docs/architecture-cpp.md` gives the shape: `librentropic-inference-{cuda,vulkan,cpu}.so` links `llama.cpp` and implements `IInferenceBackend`. The CUDA, Vulkan, and CPU variants are compile-time choices.
- The pin is the submodule commit. The code comments reference a pinned build (b8420 in older notes). `RELEASE_NOTES.md` shows later bumps, and the notes say each bump requires re-checking vendor-coupled code such as `tool_call_markers`.
- A file named `llama.h` sits at the repo root. The index holds it with no documentation and no symbols, so I can't tell whether it is the vendored header or a local shim.

**How far it reaches into entropic's source**

| Layer | Reach |
|---|---|
| `src/inference/llama_cpp_backend.{h,cpp}` | Heavy. `LlamaCppBackend` calls `llama_model_load_from_file`, `llama_init_from_model`, and the decode, sampler, and batch APIs. It holds `llama_model*`, `llama_context*`, and the MTP draft context. Its doc says it is "Versioned": a pinned-commit subclass overrides API-version-specific calls. |
| `src/inference/llama_cpp_sampler.{h,cpp}` | Wraps a `llama_sampler` chain behind entropic's abstract `Sampler` / `SamplerFactory`. |
| `src/inference/llama_cpp_tokenizer.{h,cpp}` | Forwards to `llama_tokenize` and `llama_token_to_piece` via a borrowed `llama_vocab*`. |
| Other `src/inference/` files | Touch llama.cpp indirectly. `adapter_manager.cpp` uses LoRA APIs. `image_preprocessor.cpp` uses the stb_image copy vendored with llama.cpp. `mtp_envelope.h` and `tool_call_markers.h` depend on llama.cpp behavior. |
| `include/entropic/types/config.h` | Mirrors llama.cpp settings as plain config fields (`n_batch`, `n_ubatch`, `flash_attn`, `cache_type_k/v`, `split_mode`, `offload_kqv`, `n_parallel`, `llama_log_path`). `build_cparams` maps these onto llama.cpp params. No llama.cpp types appear in this header. |
| `include/entropic/inference/speculative_compat.h` | Public header. Its doc says the compatibility check lives in entropic "not llama.cpp", so it is meant to stay llama-free. I did not confirm its body. |
| Interfaces and C API (`entropic.h`, `i_*.h`) | No llama.cpp symbols indexed. The design rules say exceptions and C++ ABI stay inside the `.so`, and the Python wrapper is generated from `entropic.h`. The index shows no llama symbols in `python/`. |
| Tests | Several unit tests mock llama.cpp at link time (`adapter_manager_test.cpp`, `speculative_compat_test.cpp`, `vocab_only_smoke_test.cpp`). They define stand-ins for `llama_adapter_lora_init` and similar functions. |

**Bottom line:** the dependency is a submodule that the inference `.so` links directly. Its reach is about seven files in `src/inference/`, plus config fields that mirror its parameters and link-time mocks in the tests. Nothing in the public C interface or the Python wrapper exposes llama.cpp types.

**Gaps:** the index does not include CMake bodies, so the exact `target_link_libraries` and FetchContent or submodule wiring is unverified. Confirm them by reading `src/inference/CMakeLists.txt` and `extern/CMakeLists.txt`.