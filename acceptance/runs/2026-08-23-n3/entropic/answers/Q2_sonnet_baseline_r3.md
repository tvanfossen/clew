I have what I need to answer.

## How the dependency is brought in

`llama.cpp` is a **git submodule**, not a package-manager dependency: `.gitmodules` points `extern/llama.cpp` at `https://github.com/ggml-org/llama.cpp.git`, currently pinned at commit `20a04b2` (the code comments reference it as "submodule pinned at b8420" in one CMake changelog note). In a bare checkout the submodule shows up as an empty gitlink directory until `git submodule update --init` is run.

Unlike the other third-party deps (spdlog, Catch2, rapidyaml, nlohmann/json, cpp-httplib), which `extern/CMakeLists.txt` pulls in via `FetchContent_Declare`/`FetchContent_MakeAvailable` at configure time, llama.cpp is vendored in-tree as a submodule and built with a plain `add_subdirectory(llama.cpp EXCLUDE_FROM_ALL)`. Two targets are pulled out of it:

- the main `llama.cpp` tree (with `LLAMA_BUILD_TESTS/EXAMPLES/SERVER/TOOLS` all forced OFF, `LLAMA_BUILD_COMMON` forced ON) — this gives the `llama`, `ggml`, and `llama-common` static targets, built with `BUILD_SHARED_LIBS OFF` and `POSITION_INDEPENDENT_CODE ON` so they can be absorbed into entropic's own `.so`.
- `llama.cpp/tools/mtmd` is separately `add_subdirectory`'d for the `mtmd` (multimodal) library, since its CLI siblings are excluded.

`ENTROPIC_HAS_CUDA` bridges straight into llama.cpp's own `GGML_CUDA` cache variable, so entropic's CUDA/Vulkan/CPU backend selection directly drives how llama.cpp itself is configured — not just how entropic links against it.

`EXCLUDE_FROM_ALL` on both subdirectories suppresses llama.cpp's own `install()` rules (it would otherwise install `libllama.a`, a CMake package config, `convert_hf_to_gguf.py`, a pkg-config file) — entropic's facade absorbs `llama`, `mtmd`, and `llama-common` as private static link dependencies (`$<LINK_ONLY:...>`) into the single shipped `librentropic.so`, so consumers of entropic never link against llama.cpp directly.

## How far it reaches into entropic's own source

It's not confined behind a thin adapter — it reaches fairly deep into `src/inference/`, and touches the facade:

- **`src/inference/llama_cpp_backend.{h,cpp}`, `llama_cpp_sampler.{h,cpp}`, `llama_cpp_tokenizer.{h,cpp}`** are the dedicated backend/sampler/tokenizer implementations of entropic's `Backend`/`Sampler`/`Tokenizer` interfaces, built directly on top of llama.cpp's public API (`<llama.h>`) plus its "common" support layer (`<common.h>`, `<chat.h>`, `<sampling.h>`, `<speculative.h>`) and multimodal layer (`<mtmd.h>`, `<mtmd-helper.h>`).
- Beyond that trio, several more inference-layer files include llama.cpp headers directly rather than going through an entropic-owned abstraction: `adapter_manager.cpp`, `grammar_registry.cpp`, `inference_c_api.cpp`, `interface_factory.cpp`, `orchestrator.cpp`, `secondary_model_loader.cpp`, `speculative_compat.cpp`, and the header `tool_call_markers.h`.
- It leaks one level further up: `src/facade/entropic.cpp` (the top-level C-API facade) includes `llama_cpp_backend.h` directly and calls `llama_model_ptr()`/`llama_context_ptr()` accessors to hand raw llama.cpp handles (`llama_model*`, `llama_context*`) to the adapter-management (LoRA) code — so the facade layer knows about llama.cpp types, not just the inference layer.
- Build-wise, both `src/inference/CMakeLists.txt` and `src/facade/CMakeLists.txt` add `extern/llama.cpp/{include,ggml/include,common,vendor}` as include directories, and the facade links `llama`, `mtmd`, and `llama-common` (private, absorbed into the shared lib) plus needs `extern/llama.cpp/vendor` for `stb_image.h` used in entropic's own image-preprocessing code.

So the dependency is architecturally "vendored and compiled from source as part of the build," and while the *intent* (per the CMake comments) is to keep it behind the `entropic::inference` object library and the facade boundary — llama.cpp symbols/headers stop leaking past `librentropic.so`'s exported API — internally the coupling isn't isolated to one adapter file: roughly a dozen files across `src/inference/` plus the top-level `src/facade/entropic.cpp` all `#include` llama.cpp headers and call its C API directly.
