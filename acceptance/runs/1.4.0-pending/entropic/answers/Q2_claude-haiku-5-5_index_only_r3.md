**Short answer:** llama.cpp is vendored as a git submodule under `extern/`, built into entropic's inference library, and used directly through its C API. Its types stay inside `src/inference/` and one facade function. The public headers appear to keep it out, but I checked that only partially.

**How it's brought in**

- `extern/` holds the llama.cpp submodule. `extern/CMakeLists.txt` says it is "fetched at configure time via FetchContent" and that llama.cpp "is a submodule but NOT built in v1.8.0." That comment is stale, since the code now calls the library heavily.
- `src/inference/CMakeLists.txt` says the inference library "links against llama.cpp, nlohmann/json, and spdlog." The index does not contain the actual link line, so I could not confirm the exact target wiring.
- Pinned commit: `llama_cpp_backend.cpp` says "pinned against llama.cpp submodule b8420," but `RELEASE_NOTES.md` records a bump to b9592 (`ac4cddeb`). The file-level comments are behind the current pin.

**How far it reaches**

| Layer | Files | llama.cpp usage |
|---|---|---|
| Backend | `src/inference/llama_cpp_backend.{h,cpp}` | Direct C API: `llama_model_load_from_file`, `llama_init_from_model`, decode, state save/restore, MTP and speculative decode, mtmd. The class is about 157 members. |
| Sampler / tokenizer | `llama_cpp_sampler.*`, `llama_cpp_tokenizer.*` | Adapters over `llama_sampler` chains and `llama_vocab`. |
| Adapters | `adapter_manager.cpp` | LoRA C API (`llama_adapter_lora_init`, `llama_set_adapters_lora`). |
| Orchestration | `orchestrator.cpp` | `resolve_target_model`, `check_speculative_compat`, and `llama_model_ptr()` for adapter preload and deactivate. |
| Speculative compat | `speculative_compat.cpp` | Architecture and vocab checks on `llama_model`. |
| Facade | `src/facade/entropic.cpp` | `entropic_adapter_load` checks `llama_model_ptr()`. |
| Image preprocessing | `image_preprocessor.cpp` | Uses stb_image vendored with llama.cpp. |

So the dependency reaches well into `src/inference/`. It also touches the orchestrator and one facade entry point.

**What stays contained**

- The `include/entropic/` headers I could see mention llama.cpp only in comments. A search for `llama_model` found no hits under `include/`, but that search returned only the top 40 results, so this is not exhaustive.
- The design rules in `CLAUDE.md` say no third-party headers in interface contracts and that the C ABI is opaque handles. The index is consistent with that, though I did not verify each header.
- Tests replace llama.cpp with link-time mocks (`adapter_manager_test.cpp`, `speculative_compat_test.cpp`). Some tests, such as `grammar_engagement_test.cpp`, use the real `llama_model_free` on a vocab-only model.

**Limits:** The index does not parse `extern/` (the vendored tree) or the top-level CMake file, and `llama.h` is not harvested. Two things need a direct read of the build files: the actual `target_link_libraries` line and the submodule's pinned SHA.