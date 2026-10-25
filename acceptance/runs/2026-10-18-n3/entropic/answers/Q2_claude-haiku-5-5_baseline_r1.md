**Short answer:** llama.cpp is vendored as a git submodule at `extern/llama.cpp` (pinned to `20a04b22`, with the comment in `extern/CMakeLists.txt` saying "pinned at b8420"), and CMake builds it straight into the engine as a static library via `add_subdirectory`. It reaches the engine's own `.cpp` files, but not its public headers.

**How it's brought in**

- `.gitmodules` maps `extern/llama.cpp` to `github.com/ggml-org/llama.cpp`.
- The top-level `CMakeLists.txt:134` runs `add_subdirectory(extern)`. Everything else (spdlog, Catch2, ryml, nlohmann/json, cpp-httplib) comes in through `FetchContent`, but llama.cpp does not.
- `extern/CMakeLists.txt` configures llama.cpp, then adds it:
  - Forces `LLAMA_BUILD_TESTS/EXAMPLES/SERVER` off, `LLAMA_BUILD_COMMON` on, and `LLAMA_BUILD_TOOLS` off.
  - Maps `ENTROPIC_HAS_CUDA` to `GGML_CUDA`, and sets `GGML_CUDA_GRAPHS` from `ENTROPIC_CUDA_GRAPHS`, which defaults off.
  - Forces static libraries and position-independent code.
  - Calls `add_subdirectory(llama.cpp EXCLUDE_FROM_ALL)`, so no upstream install rules fire.
  - Also adds `llama.cpp/tools/mtmd` for multimodal support, again with `EXCLUDE_FROM_ALL`.
- `src/inference/CMakeLists.txt` links the inference library against the `llama` and `llama-common` targets and adds `extern/llama.cpp/vendor` and `extern/llama.cpp/common` to its include path.

**How far it reaches into entropic's source**

The reach is limited to the inference layer.

- **Direct `#include <llama.h>` or `<chat.h>`:** `speculative_compat.cpp`, `adapter_manager.cpp`, `orchestrator.cpp`, `grammar_registry.cpp`, and `tool_call_markers.h` (which includes `chat.h`). `llama_cpp_backend.h` also includes `llama.h`.
- **Through `llama_cpp_backend.h`:** `llama_cpp_backend.cpp`, `llama_cpp_sampler.cpp`, `llama_cpp_tokenizer.cpp`, `interface_factory.cpp`, `secondary_model_loader.cpp`, `inference_c_api.cpp`, and `src/facade/entropic.cpp`. The facade is the one place outside `src/inference/` that sees llama types.
- **Public headers:** `include/entropic/` does not include llama.h. The `llama_*` mentions there are doc comments, or types like `llama_seq_id` and `llama_split_mode` referenced in comments. `config.h` mirrors llama.cpp parameter names as its own fields. The public C API is `entropic.h`.
- **Tests:** several model and unit tests include llama.h directly.

So the design rules hold on the surface: the C interface stays opaque and the `.so` boundary has no llama.cpp types. The facade (`entropic.cpp`) is the one exception outside the inference directory, and it reaches llama only through the backend header.

**Things I noticed**

- **The submodule is empty in this checkout.** `git submodule status` shows `-20a04b…` (uninitialized), and `extern/llama.cpp/` is an empty directory. A configure will fail at `add_subdirectory(llama.cpp …)` until `git submodule update --init extern/llama.cpp` is run. I did not run that.
- **A stale comment.** `extern/CMakeLists.txt` says "llama.cpp is a submodule but NOT built in v1.8.0", but the same file now builds it. The comment is out of date.