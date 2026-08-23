I have a clear picture now. Here's the answer.

## How the dependency is brought in

`llama.cpp` is vendored as a **git submodule**, not a package-manager dependency:

```
.gitmodules:  [submodule "extern/llama.cpp"] → https://github.com/ggml-org/llama.cpp.git
              pinned commit b8420...
```

At configure time, `extern/CMakeLists.txt` does `add_subdirectory(llama.cpp EXCLUDE_FROM_ALL)`, building `libllama.a` (and `libmtmd.a` from `llama.cpp/tools/mtmd` for multimodal) as **static** libraries with `LLAMA_BUILD_TESTS/EXAMPLES/SERVER/TOOLS` all off and `LLAMA_BUILD_COMMON=ON` (needed only so `mtmd`'s CMake can reference the `common` target). `EXCLUDE_FROM_ALL` suppresses llama.cpp's own install rules — entropic's facade absorbs `libllama.a` statically, so downstream consumers of entropic never link llama.cpp directly. GPU support is bridged via `ENTROPIC_HAS_CUDA → GGML_CUDA`. Everything else in the repo (spdlog, Catch2, ryml/rapidyaml) comes in via `FetchContent`; llama.cpp is the one dependency handled as a submodule instead, presumably because it's pinned to an exact commit and patched/tracked deliberately (comments reference "v2.1.11-pinned commit `253ba110b`", "b8420", etc.).

## How far it reaches into entropic's own source

It reaches **deep into the inference layer**, but is deliberately walled off from the public C API:

- **Direct wrapper files** — `src/inference/llama_cpp_backend.{h,cpp}`, `llama_cpp_sampler.{h,cpp}`, `llama_cpp_tokenizer.{h,cpp}` `#include <llama.h>` directly and implement entropic's `IInferenceBackend`/`ISampler`/`ITokenizer` interfaces against the raw llama.cpp C API.
- **Several other `.cpp` files in `src/inference/`** also `#include <llama.h>` directly: `adapter_manager.cpp`, `speculative_compat.cpp`, `grammar_registry.cpp`, `orchestrator.cpp` — plus `interface_factory.cpp`, `secondary_model_loader.cpp`, and `inference_c_api.cpp` which pull in `llama_cpp_backend.h`.
- **Public headers leak llama.cpp types via forward declarations**, not full includes: `include/entropic/inference/adapter_manager.h`, `orchestrator.h`, and `speculative_compat.h` forward-declare `struct llama_model`, `llama_context`, `llama_adapter_lora` and expose them in function signatures (`llama_model*`, `llama_context*`). So llama.cpp's type names appear in entropic's own public interface headers, even though the real `<llama.h>` isn't included there.
- **Build-level reach**: `src/inference/CMakeLists.txt` adds `extern/llama.cpp/common` and `extern/llama.cpp/vendor` (for `stb_image.h`) as private include dirs, and links `llama`, `llama-common`, and `mtmd` — so entropic reaches past `llama.h` itself into llama.cpp's `common/` helper code (`common.h`, `sampling.h`, `speculative.h`) and its vendored third-party headers.
- **A compatibility shim exists specifically because of an upstream limitation**: `speculative_compat.{h,cpp}` explicitly documents that it duplicates logic from `extern/llama.cpp/common/speculative.cpp` because that check is `static`/file-private in llama.cpp at the pinned commit and can't be called directly — so entropic re-implements it.
- **Tests reach in too**: `tests/model/*.cpp` (real-model tests) and several `tests/unit/inference/*.cpp` files exercise the llama.cpp-backed code paths directly (e.g. `backend_real_model_smoke_test.cpp`, `vocab_only_smoke_test.cpp`).

So the boundary is: `IInferenceBackend`/`ISampler`/`ITokenizer` interfaces plus opaque/forward-declared `llama_model*`/`llama_context*` pointers form the seam, but the seam is porous at the header level (raw llama.cpp pointer types appear in entropic's own headers) and the inference `.so` as a whole is thoroughly built against llama.cpp's C API and its `common/` support code, not just a thin binding layer.
