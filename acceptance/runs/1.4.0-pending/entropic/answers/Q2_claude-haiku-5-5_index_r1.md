**Short answer:** llama.cpp is vendored as a git submodule and compiled into entropic's shared library. Its types are not part of the public C API, but they reach well into the internal inference layer and leak into a few public C++ headers.

**How it's brought in**

- `.gitmodules` registers `extern/llama.cpp` (ggml-org/llama.cpp). It is not FetchContent, unlike spdlog, ryml, json, httplib and Catch2 in `extern/CMakeLists.txt`.
- `extern/CMakeLists.txt` calls `add_subdirectory(llama.cpp EXCLUDE_FROM_ALL)`. It also adds `llama.cpp/tools/mtmd` for multimodal. Options are forced: tests, examples, server and tools are off, and `LLAMA_BUILD_COMMON` is on. Static linking is forced by saving and clearing `BUILD_SHARED_LIBS`.
- CUDA is bridged via `ENTROPIC_HAS_CUDA` → `GGML_CUDA`.
- `src/inference/CMakeLists.txt` links `llama`, `mtmd` (PRIVATE) and `llama-common` (PUBLIC) into the inference object library. It also adds `extern/llama.cpp/vendor` and `common` as private include paths.
- `src/facade/CMakeLists.txt` links `llama`, `mtmd` and `llama-common` as `LINK_ONLY` PRIVATE, so they are absorbed into `librentropic.so`. Consumers never link llama directly. Facade private includes add `extern/llama.cpp/include` and `ggml/include`.

**Current state of this checkout**

- `git submodule status` shows `-20a04b22… extern/llama.cpp`. The `-` means uninitialized, and `extern/llama.cpp/` is empty.
- A fresh checkout therefore needs `git submodule update --init` before configure. Without it, `add_subdirectory` should fail. I did not run configure to confirm.
- The version pins disagree across files. The CMake comment says "pinned at b8420". `speculative_compat.h` cites commit `253ba110b`. The gitlink points at `20a04b22`. Worth reconciling.
- The `extern/CMakeLists.txt` header comment ("NOT built in v1.8.0") is stale; the code builds it.

**How far it reaches into entropic's source**

```
public C API (entropic.h)        no llama types; state blobs are opaque bytes
public C++ headers (include/)    no #include <llama.h>, but forward-declares
  inference/orchestrator.h         llama_model / llama_context / llama_adapter_lora
  inference/adapter_manager.h      and exposes them in method signatures
  inference/speculative_compat.h
  types/config.h                   fields mirror llama params (n_ubatch, split_mode…)
                 │
src/inference/ (internal)        #include <llama.h> directly in:
  llama_cpp_backend.h (+.cpp)      LlamaCppBackend: model_, ctx_, vocab_, mtmd_ctx_
  llama_cpp_sampler / tokenizer    builds llama_sampler chains, tokenizes via vocab
  grammar_registry, orchestrator   llama_sampler_init_grammar, speculative kernel
  adapter_manager, speculative_compat
                 │
src/facade/entropic.cpp          #includes llama_cpp_backend.h; dynamic_casts to
                                 LlamaCppBackend to pull llama_model_ptr()
                                 and llama_context_ptr() for adapter load/unload
```

- Direct `<llama.h>` includes: 7 files under `src/inference/`, plus tests.
- Files that include `llama_cpp_backend.h` or `orchestrator.h` also pick up llama types transitively. That includes `entropic.cpp`, `engine_handle.h`, `inference_c_api.cpp`, `interface_factory.cpp` and `secondary_model_loader.cpp`. I did not compute the full transitive closure.
- Design rule 6 in `.claude/CLAUDE.md` says no third-party headers in interface contracts. The forward declarations do not technically include llama headers, but `orchestrator.h` and `adapter_manager.h` put llama pointers in public signatures. That is a violation of the rule's intent. Those headers are under `include/`, so they are in the installed surface. Since interface headers are immutable without a proposal, this needs a decision rather than a quiet fix.

**Bottom line:** the dependency is compiled and absorbed into the facade `.so` via a submodule and PRIVATE links, so consumers see only the C API. Internally, llama types run through the backend, sampler, tokenizer, orchestrator and adapter layers. They are visible in some public C++ interface headers, and the facade reaches into the concrete backend to get raw llama handles.