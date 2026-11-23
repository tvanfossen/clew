**Short answer:** llama.cpp is vendored as a git submodule and compiled into the engine's shared library at build time. It is not a runtime or system dependency. Its types are mostly confined to the inference layer, but a few are forward-declared in public headers and used across the facade boundary.

**How it's brought in**

- `.gitmodules` maps `extern/llama.cpp` to `ggml-org/llama.cpp`. The superproject pins it at commit `20a04b22`.
- `extern/CMakeLists.txt` calls `add_subdirectory(llama.cpp EXCLUDE_FROM_ALL)` with `LLAMA_BUILD_TESTS/EXAMPLES/SERVER/TOOLS=OFF` and `LLAMA_BUILD_COMMON=ON`. It also pulls in `llama.cpp/tools/mtmd` for multimodal. `GGML_CUDA` is forced on when CUDA is detected.
- The comment says `EXCLUDE_FROM_ALL` exists so consumers never link llama directly. It is absorbed as static code into `librentropic.so`.
- The other third-party deps (spdlog, ryml, Catch2, nlohmann/json, cpp-httplib) come in via `FetchContent`, not a submodule. SQLite is a system `find_package`.

**Where it reaches**

```
include/entropic/            public headers (C ABI + C++ interfaces)
  ├─ entropic.h / i_inference_backend.h   C ABI; llama only in log-control doc comments
  └─ inference/{sampler,orchestrator,adapter_manager,speculative_compat}.h
        forward-declare struct llama_model / llama_context,
        and take llama_model*/llama_context* in signatures
src/inference/   (llama.h, chat.h, sampling.h, mtmd.h)
  ├─ llama_cpp_backend.{h,cpp}   the real llama.cpp owner
  ├─ llama_cpp_sampler / tokenizer, orchestrator, adapter_manager,
  │  speculative_compat, grammar_registry, tool_call_markers.h
  └─ adapters/*  (qwen35, qwen36, nemotron3)
src/facade/entropic.cpp   includes llama_cpp_backend.h, dynamic_casts to
                          LlamaCppBackend, calls llama_model_ptr()/llama_context_ptr()
tests/                    include llama.h directly in unit and model tests
python/                   no llama references
```

So the reach is:

- **Pervasive inside the inference library**, where `#include <llama.h>` appears in about ten `src/inference` files.
- **Leaked as opaque pointers into several public C++ headers.** The `include/entropic/inference/*.h` files forward-declare the llama structs and expose `llama_model*` and `llama_context*` in signatures. Consumers never need `llama.h` to compile against them, but they do see the names.
- **Absent from the C ABI surface** (`entropic.h`) apart from the log-redirect functions, which are documented in terms of llama/ggml logs.
- **Absent from the Python bindings** (`python/` has no llama references).

**Things to check**

- In this working tree `extern/llama.cpp/` is an empty directory. The submodule is not initialized, so `add_subdirectory(llama.cpp)` will fail until `git submodule update --init extern/llama.cpp` runs. I did not configure or build, so I have not confirmed that failure directly.
- The pin is described inconsistently in comments. `extern/CMakeLists.txt` says "pinned at b8420", while `speculative_compat.h`, `config.h`, and several tests say `253ba110b`. The gitlink is `20a04b22`. Those comments are stale or refer to different pins, and the mismatch is worth reconciling.