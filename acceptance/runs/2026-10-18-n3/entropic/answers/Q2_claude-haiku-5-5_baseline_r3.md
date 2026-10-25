**Short answer:** llama.cpp is a git submodule at `extern/llama.cpp`, pinned to commit `20a04b22`, which is built from source with CMake and absorbed statically into `librentropic.so`. Its C++ headers reach into the inference and facade sources, and a few llama type names leak into public headers, but no llama types appear in the C ABI (`entropic.h`).

**How it's brought in**

1. `.gitmodules` registers `extern/llama.cpp` from `ggml-org/llama.cpp`.
2. `extern/CMakeLists.txt` sets the llama build options (`LLAMA_BUILD_COMMON=ON`, tests, examples, server and tools off, CUDA bridged from `ENTROPIC_HAS_CUDA`) and then calls `add_subdirectory(llama.cpp EXCLUDE_FROM_ALL)`. It also adds `llama.cpp/tools/mtmd` for multimodal support.
3. Consumers of the build link to targets by name: `llama`, `llama-common`, and `mtmd`.
4. `src/inference/CMakeLists.txt` links those targets into the inference object library. `src/facade/CMakeLists.txt` links them `$<LINK_ONLY:>` into `entropic-facade`, so they are absorbed into the shared library.
5. The installed package config (`cmake/entropic-config.cmake.in`) declares no llama dependency. Consumers link only `entropic::entropic`.

Other dependencies (spdlog, ryml, json, httplib) follow the same absorb-into-facade pattern.

**How far it reaches into entropic's source**

| Layer | Files | Use of llama |
|---|---|---|
| Private backend (`src/inference/`) | `llama_cpp_backend.cpp/.h`, `llama_cpp_sampler.cpp`, `llama_cpp_tokenizer.cpp`, `orchestrator.cpp`, `adapter_manager.cpp`, `grammar_registry.cpp`, `speculative_compat.cpp` | Direct `#include <llama.h>`. The backend also includes `common.h`, `chat.h`, `sampling.h`, `speculative.h`, `mtmd.h`, and `mtmd-helper.h`. |
| Private headers | `llama_cpp_sampler.h`, `llama_cpp_tokenizer.h` | Forward-declare opaque llama types to keep `llama.h` out of the header. |
| Facade | `src/facade/entropic.cpp` | Includes `llama_cpp_backend.h`, so it sees llama types indirectly. |
| Public headers (`include/entropic/`) | `inference/adapter_manager.h`, `inference/orchestrator.h`, `inference/speculative_compat.h` | Forward-declare `struct llama_model/llama_context/llama_adapter_lora` and use them in method signatures. No `#include`, but the names leak. |
| Public C ABI | `entropic.h` | No llama types. Mentions llama only in comments, e.g. the state blob is "bit-for-bit llama.cpp `llama_state_get_data` output." |
| Tests | `tests/unit/inference/*`, `tests/model/*` | Include `llama.h` and `chat.h` directly. |

Two things to note:

- The public-header forward declarations contradict the stated rule that third-party headers stay out of interface contracts. The declarations don't pull in the llama header, but the names are part of the exported surface.
- The `common` library (`llama-common`) is a dependency too, not just core llama. The backend's chat parsing and speculative decoding rely on it.

**Verified in this checkout:** `git submodule status` shows `-20a04b22… extern/llama.cpp`. The leading `-` means uninitialized, and the directory is empty. A configure will fail at `add_subdirectory(llama.cpp)` until you run `git submodule update --init --recursive`. CI sets `submodules: recursive` in its checkout steps, so it's only a local-clone trap. I did not run a configure or build to confirm the exact failure message.