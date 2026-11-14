**Short answer:** llama.cpp is a git submodule fetched and built from source by CMake, then linked statically into `librentropic.so`. Its headers are used only inside `src/`, and the public `include/` tree never includes them. Llama types do leak into a few public headers, but only as forward-declared opaque names and pointers.

**How it's brought in**

- `.gitmodules` maps `extern/llama.cpp` to ggml-org/llama.cpp.
- `extern/CMakeLists.txt` (included from the top-level `CMakeLists.txt:134`) configures it. It forces `LLAMA_BUILD_TESTS/EXAMPLES/SERVER/TOOLS` off and `LLAMA_BUILD_COMMON` on, and bridges `ENTROPIC_HAS_CUDA` to `GGML_CUDA`.
- It then calls `add_subdirectory(llama.cpp EXCLUDE_FROM_ALL)` and separately adds `llama.cpp/tools/mtmd` for multimodal support. The comments say the upstream install rules are suppressed and the facade "absorbs `libllama.a` as a static dependency."
- Everything else in `extern/` (spdlog, Catch2, ryml, json, httplib) comes through `FetchContent`. llama.cpp is the only dependency that comes from a submodule.

**Where it's linked**

- `src/inference/CMakeLists.txt`: the inference object library links `llama` and `mtmd` PRIVATE, and `llama-common` PUBLIC. It also adds `extern/llama.cpp/{vendor,common}` as private include dirs.
- `src/facade/CMakeLists.txt`: `librentropic` takes `llama`, `mtmd` and `llama-common` as `LINK_ONLY` PRIVATE dependencies, so they are absorbed into the shared library. The facade also adds `extern/llama.cpp/include` and `ggml/include` as private include paths.
- Consumers never link llama directly.

**How far it reaches into the source**

llama.cpp headers are included by about 9 files under `src/inference/`:

| Layer | Files |
|---|---|
| Wrapper implementation | `llama_cpp_backend.{h,cpp}`, `llama_cpp_sampler.cpp`, `llama_cpp_tokenizer.cpp` |
| Subsystems | `orchestrator.cpp`, `adapter_manager.cpp`, `speculative_compat.cpp`, `grammar_registry.cpp`, `tool_call_markers.h` |
| Facade | `src/facade/entropic.cpp` reaches it only indirectly, through `llama_cpp_backend.h` |

`LlamaCppBackend` (`src/inference/llama_cpp_backend.h:65`) is the main consumer. It is an `InferenceBackend` subclass that owns `llama_model*`, `llama_context*`, `mtmd` and sampler state, and it uses the `common_chat`, `common_speculative` and `common_sampler` helpers. `interface_factory.cpp`, `inference_c_api.cpp` and `secondary_model_loader.cpp` route through it.

Public headers under `include/entropic/` reference llama only in two ways:

- **Forward declarations and pointer parameters.** `orchestrator.h`, `adapter_manager.h`, `sampler.h`, `speculative_compat.h` and `types/config.h` forward-declare `struct llama_model/llama_context/llama_vocab` and take those pointers. Example: `Orchestrator::deactivate_if_active(llama_context*)` at `orchestrator.h:759`. The C API `entropic.h` has llama mentions only in comments.
- **Comments.** The logging redirect in `i_inference_backend.h` refers to llama/ggml logs.

No public header includes `llama.h`, `ggml.h` or `mtmd.h`, and no `src/` file under the facade's public surface exposes them as values. The Python package (`python/`) has no llama references.

Tests are the other real consumer: several `tests/unit/inference` and `tests/model` files include `llama.h` and `chat.h` directly.

**Things I could not confirm or noticed**

- **The submodule is not checked out here.** `extern/llama.cpp/` is an empty directory, and `git submodule status` shows `-20a04b22…`, meaning uninitialized. So I could not read llama.cpp's own CMake or confirm the actual pinned commit. The `extern/CMakeLists.txt` comments and `docs/architecture-cpp.md` say the pin is b8420, but the gitlink hash is `20a04b22`. Those two sources disagree, or the comment is stale; I'd check which one is authoritative before relying on the version.
- **The `common` dependency is larger than the comment suggests.** The header comments describe `common` as a helper library, but `llama_cpp_backend.cpp` depends on `chat.h`, `sampling.h`, `speculative.h`, and `mtmd*.h`. Those are upstream internals, not a stable C API, so every llama.cpp bump is a risk point for this file.