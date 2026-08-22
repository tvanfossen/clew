## Bringing it in

llama.cpp is a **git submodule**, not a package dependency:

```
[submodule "extern/llama.cpp"]
    path = extern/llama.cpp
    url = https://github.com/ggml-org/llama.cpp.git
```

Pinned currently at `20a04b22` (`gguf-v0.19.0-840-g20a04b220`). It's pulled into the CMake build from `extern/CMakeLists.txt` via `add_subdirectory(llama.cpp EXCLUDE_FROM_ALL)`, alongside a second `add_subdirectory` for `llama.cpp/tools/mtmd` (multimodal support, added v2.1.8). Both are built as **static** libraries with PIC forced on and then linked into entropic's own inference shared library — the comment in the build file is explicit about the intent: *"Our facade absorbs libllama.a as a static dependency; consumers never link to llama directly."* So it's vendored-and-baked-in, not shipped as a sibling `.so`. `ENTROPIC_HAS_CUDA` bridges straight to `GGML_CUDA` for GPU builds, and `LLAMA_BUILD_TESTS/EXAMPLES/SERVER/TOOLS` are all forced off so only the library and mtmd get built, not llama.cpp's CLI tools.

## How far it reaches

**Contained, mostly, in `src/inference/`.** Eight files `#include <llama.h>` or `<mtmd.h>` directly: `llama_cpp_backend.{h,cpp}` (4,100+ lines — the bulk of the coupling), `llama_cpp_sampler.{h,cpp}`, `llama_cpp_tokenizer.{h,cpp}`, plus `grammar_registry.cpp`, `speculative_compat.cpp`, `orchestrator.cpp`, and `adapter_manager.cpp`.

**The abstract interface boundary holds.** `include/entropic/interfaces/i_inference_backend.h` — the immutable interface header per the project's own design rules — has zero llama.cpp types in it, only comment references. That's the intended seam and it's clean.

**But it leaks one layer above the interface.** `include/entropic/inference/adapter_manager.h`, `orchestrator.h`, and `speculative_compat.h` (implementation-layer headers, distinct from `interfaces/`) forward-declare `llama_model`, `llama_context`, and `llama_adapter_lora` and use them as real parameter/member types in their public signatures — not just comments. So llama.cpp's opaque struct types are baked into several internal C++ header contracts, beyond just the `.cpp` files that own the actual llama.cpp calls.

**The public C API (`entropic.h`) itself stays pure** — no llama.cpp types cross that `.so` boundary, consistent with the architecture doc's rule #1. But the implementation behind it, `src/facade/entropic.cpp`, does reach in for the LoRA adapter endpoints (`entropic_adapter_load/unload/swap`): it `dynamic_cast<LlamaCppBackend*>(base)`s the abstract backend back down to the concrete llama.cpp type and pulls out raw `llama_model*`/`llama_context*` via `llama_model_ptr()`/`llama_context_ptr()` to hand to the adapter manager. The inline comments acknowledge this isn't backend-agnostic ("The C API cannot safely provide this — use tier-based adapter configuration for lifecycle management") — it's a known, documented gap in the abstraction, not an oversight.

**Config schema mirrors llama.cpp's surface directly.** `include/entropic/types/config.h` and `src/config/loader.cpp` carry llama.cpp-specific vocabulary as first-class config fields/comments — `llama_split_mode`, `llama_log_path`, `n_ubatch`, adapter WARM/HOT states documented against `llama_adapter_lora_init`/`llama_set_adapter_lora` — so entropic's own configuration model is shaped around llama.cpp's parameter names rather than abstracting them behind engine-neutral terms.

**Net picture:** the dependency is vendored via submodule, statically absorbed into entropic's shared library so nothing downstream links llama.cpp directly, and the C API surface is genuinely insulated. But the C++ internals — one layer of headers up from the interface, the adapter/LoRA code path in the facade, and the config schema — all know they're talking to llama.cpp specifically. If a second inference backend were ever added, `i_inference_backend.h` would be ready for it, but `adapter_manager`, `orchestrator`, `speculative_compat`, and the facade's adapter endpoints would need rework since they currently assume llama.cpp's concrete types.
