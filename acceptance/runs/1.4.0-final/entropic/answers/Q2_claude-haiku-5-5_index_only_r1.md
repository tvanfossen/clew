**Short answer:** llama.cpp enters the build as a vendored source tree under `extern/`, and only the `src/inference/` layer uses its API. I could not confirm the build wiring from the index.

**How it's brought in (what I could verify):**
- The file-level docs in `src/inference/llama_cpp_backend.cpp` say it is "pinned against llama.cpp submodule b8420", so the pin is a git submodule. The docs also cite `extern/llama.cpp/common/chat-peg-parser.cpp:442-443` from `src/inference/tool_call_markers.h`, which places the source at `extern/llama.cpp`.
- The index does not hold the build scripts. A search for `add_subdirectory llama` returned nothing, and `extern` is not indexed (`external_files: 0`). So I cannot see the CMake target, the linkage, or how the submodule is fetched. Those need a read of the CMake files or `.gitmodules`.

**How far it reaches into entropic's source:**
- **Inside `src/inference/`, the llama.cpp API is used directly.** Seven indexed files touch it: `llama_cpp_backend.{h,cpp}`, `llama_cpp_sampler.{h,cpp}`, `llama_cpp_tokenizer.{h,cpp}`, and `adapter_manager.cpp` (LoRA via `llama_adapter_lora_*`). The backend's `llama_model_ptr()` and `llama_context_ptr()` accessors expose the raw llama types. Its header describes it as "internal to inference .so".
- **It is wrapped by a thin subclass pattern.** `LlamaCppBackend` is the common 15% layer. Its header says a pinned-commit subclass (`LlamaCppBackend_b8420`) overrides version-specific calls. I did not find that subclass in the index.
- **It is used via the C API.** `entropic_create_inference_backend` in `src/inference/inference_c_api.cpp:594` constructs `new entropic::LlamaCppBackend()`, so the C++ type stays behind the C boundary.
- **One leak above the inference layer.** `src/inference/orchestrator.cpp:458` (`stage_active_tools`) does `dynamic_cast<LlamaCppBackend*>`, so the orchestrator knows the concrete backend type.
- **The public headers stay clean.** Searching `include/` finds no llama.cpp API symbols. The only hit is the config field `llama_log_path` in `include/entropic/types/config.h`, which is a name, not a dependency.
- **Tests mock the C API.** `tests/unit/inference/adapter_manager_test.cpp`, `speculative_compat_test.cpp`, and `vocab_only_smoke_test.cpp` define stand-ins for `llama_adapter_lora_*` and `llama_vocab_*`. This implies a CPU-only unit gate that does not need the real library.

**Gaps:** The index does not show the CMake wiring, the submodule's own sources, or whether the `common/` helpers (chat parser, sampler) are compiled in. The file-level comments mention `common/` and `mtmd`, but I could not confirm those are linked.