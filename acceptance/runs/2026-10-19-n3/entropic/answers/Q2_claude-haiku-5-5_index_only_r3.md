**Short answer:** llama.cpp comes in as a git submodule at `extern/llama.cpp`, linked directly with no wrapper. Its C API is used inside the inference backend layer, and the reach stops at the `IInferenceBackend` interface. The index does not show llama types in the public `include/entropic` headers, though I could not fully confirm that.

**How it is brought in**

- `docs/architecture-cpp.md` lists `extern/llama.cpp/` as a Git submodule in the project tree.
- The v1.8.0 roadmap entry says "llama.cpp as git submodule (direct linkage, no wrapper)".
- `docs/architecture-cpp.md` gives the `librentropic-inference-{cuda,vulkan,cpu}.so` libraries a link dependency on `llama.cpp`. Those three are the compile-time backend variants.
- The index does not parse CMake, so I could not read the build wiring itself.
- The pin history is inconsistent. `llama_cpp_backend.cpp` says it is pinned to submodule `b8420`. `RELEASE_NOTES.md` records a bump from `253ba110b` to `ac4cddeb` (b9592, 2026-06-11). Comments in `llama_cpp_backend.h` still cite `253ba110b`, so those comments are probably stale.

**How far it reaches into entropic's source**

| Layer | llama.cpp use |
|---|---|
| `src/inference/llama_cpp_backend.{h,cpp}` | Full use: `llama_model`, `llama_context`, decode loop, chat templates, `common_chat` parsing, state save/restore, and the MTP and speculative kernels. |
| `src/inference/llama_cpp_sampler.{h,cpp}` | Wraps a `llama_sampler` chain behind the `Sampler` / `SamplerFactory` interfaces. |
| `src/inference/llama_cpp_tokenizer.{h,cpp}` | Wraps `llama_vocab` behind the `Tokenizer` interface. |
| `src/inference/adapter_manager.cpp`, `speculative_compat.cpp` | Call `llama_set_adapters_lora` and `llama_vocab_*` directly. |
| `src/inference/image_preprocessor.cpp` | Uses `stb_image`, which is vendored with llama.cpp. |
| `include/entropic/interfaces/i_inference_backend.h` | Declares backend-neutral log functions (`entropic_inference_log_silence`, `_log_to_file`). The name `llama_log_path` appears in `include/entropic/types/config.h`. |
| `tests/unit/inference/*` | Mock `llama_*` functions at link time (for example `llama_adapter_lora_init`, `llama_vocab_n_tokens`), so CPU unit tests do not need the real library. |

`LlamaCppBackend` is the "15% layer" that subclasses `entropic::InferenceBackend`. The C ABI sits above that and does not expose llama types. This matches design rule 1 in `.claude/CLAUDE.md`, which keeps C++ and llama types from crossing the `.so` boundary. The docs also say interface contracts must not contain third-party headers.

**Limits of this answer**

- The symbol search for `llama` was capped at 50 results, so I did not check every `include/` header for a leaked `llama_*` type.
- The index does not cover CMake, the submodule metadata, or `Doxyfile`, so the build wiring and exact current pin are unverified here.