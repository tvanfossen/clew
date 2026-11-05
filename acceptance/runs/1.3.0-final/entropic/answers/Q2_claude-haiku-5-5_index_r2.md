**Short answer:** llama.cpp is a git submodule at `extern/llama.cpp`, built from source into the engine's shared library through CMake. Its reach into entropic's source is wide inside `src/inference/` and the facade, but stops at the public C ABI and the public C++ interface headers.

**How it's brought in**

- `.gitmodules` registers `extern/llama.cpp` (ggml-org/llama.cpp). The gitlink is pinned at `20a04b2`.
- `extern/CMakeLists.txt` sets the llama build options (`LLAMA_BUILD_TESTS/EXAMPLES/SERVER/TOOLS` OFF, `LLAMA_BUILD_COMMON` ON). It then runs `add_subdirectory(llama.cpp EXCLUDE_FROM_ALL)` and a second `add_subdirectory` for `llama.cpp/tools/mtmd`. Both are static (`BUILD_SHARED_LIBS` forced OFF). CUDA is enabled through `ENTROPIC_HAS_CUDA → GGML_CUDA`.
- `src/inference/CMakeLists.txt` links the inference object library to `llama`, `mtmd` (PRIVATE) and `llama-common` (PUBLIC). Its private include paths include `extern/llama.cpp/vendor` and `extern/llama.cpp/common`.
- `src/facade/CMakeLists.txt` links `llama`, `mtmd` and `llama-common` as `LINK_ONLY` PRIVATE, so they are absorbed into `librentropic.so`. Consumers never link llama directly.

**Reach into entropic's source**

| Layer | Files that include llama headers | Notes |
|---|---|---|
| `src/inference/` (core user) | `llama_cpp_backend.{h,cpp}`, `llama_cpp_sampler.cpp`, `llama_cpp_tokenizer.cpp`, `orchestrator.cpp`, `adapter_manager.cpp`, `grammar_registry.cpp`, `speculative_compat.cpp`, `tool_call_markers.h` | `llama_cpp_backend.cpp` pulls `common.h`, `chat.h`, `sampling.h`, `speculative.h`, `mtmd.h`, `mtmd-helper.h`. |
| Transitive through `llama_cpp_backend.h` | `interface_factory.cpp`, `secondary_model_loader.cpp`, `inference_c_api.cpp`, `src/facade/entropic.cpp` | These include the backend header, which includes `llama.h`, but do not include llama headers directly. |
| Public C++ interfaces (`include/entropic/inference/`) | `speculative_compat.h` only | It forward-declares `struct llama_model;` and takes `llama_model*`. Other mentions in `sampler.h` and `grammar_registry.h` are comments. |
| Public C ABI (`include/entropic/entropic.h`) | none | Pure C, with no llama types. |
| Tests | 6 files under `tests/` include llama headers | `tests/unit/inference/` mocks `llama_*` C functions at link time. `tests/model/` uses real models. |

So the dependency is contained: llama.cpp types live in the inference .so and never reach the C ABI. The one exception is the `llama_model` forward declaration in `speculative_compat.h`.

**Things I noticed**

- **The submodule is empty in this checkout.** `extern/llama.cpp/` is an empty directory, and `git submodule status` shows the `-` prefix (uninitialized). A build needs `git submodule update --init extern/llama.cpp` first. I did not run a build.
- **A comment in `extern/CMakeLists.txt` is stale.** It says "llama.cpp is a submodule but NOT built in v1.8.0", but the same file builds it, and the comment below it says v1.8.2.
- **`llama-common` is linked PUBLIC from the inference target.** Its include paths therefore propagate to anything that links `entropic::inference`. The other llama-side targets are PRIVATE. This may be intentional, but it is the one link that is not contained.