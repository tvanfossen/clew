This is a fairly deep, non-superficial dependency — not just linked as a black-box shared library. Concretely:

**How it's brought in**

- Vendored as a git submodule: `.gitmodules` points `extern/llama.cpp` at `https://github.com/ggml-org/llama.cpp.git`, pinned to a specific commit (comments reference `b8420` at the CMake level, and `253ba110b` specifically in `speculative_compat.h`).
- `extern/CMakeLists.txt` pulls it into the build with `add_subdirectory(llama.cpp EXCLUDE_FROM_ALL)`, forcing it static (`BUILD_SHARED_LIBS OFF`) and PIC, with `LLAMA_BUILD_TESTS/EXAMPLES/SERVER/TOOLS` all off so only the library code builds, not llama.cpp's own CLI/server binaries.
- It also separately pulls in `llama.cpp/tools/mtmd` (the multimodal library) as its own subdirectory, added in gh#37/v1.9.11, reusing `LLAMA_BUILD_COMMON`/`LLAMA_INSTALL_VERSION` internals from the submodule's own CMake scope.
- `EXCLUDE_FROM_ALL` also suppresses llama.cpp's install rules (`libllama.a`, `llama-config.cmake`, `convert_hf_to_gguf.py`, `llama.pc`) — the comment is explicit that "our facade absorbs libllama.a as a static dependency; consumers never link to llama directly." CUDA support is bridged via `ENTROPIC_HAS_CUDA` → `GGML_CUDA`.

**How far it reaches into entropic's own source**

It's not confined to a single adapter file — it reaches into several layers:

1. **Direct `#include <llama.h>` / `<mtmd.h>` / `<mtmd-helper.h>`** in `src/inference/`: `llama_cpp_backend.{h,cpp}`, `llama_cpp_tokenizer.cpp`, `llama_cpp_sampler.cpp`, `grammar_registry.cpp`, `speculative_compat.cpp`, `orchestrator.cpp`, and `adapter_manager.cpp`. These are the real implementation classes that call llama.cpp's C API directly (`llama_decode`, `llama_sampler_chain`, `llama_sampler_init_grammar`, `llama_adapter_lora_init`, `llama_state_get_data`, etc.).
2. **Public headers carry forward-declared llama types**, not just opaque `void*`: `include/entropic/inference/adapter_manager.h`, `orchestrator.h`, and `speculative_compat.h` forward-declare `struct llama_model`, `llama_context`, `llama_adapter_lora` and expose them in method signatures (`activate(const std::string&, llama_context* ctx)`, etc.). So llama.cpp's type identities leak into entropic's own interface layer, even though the interface headers don't `#include <llama.h>` themselves.
3. **`src/facade/entropic.cpp`** (the top-level C-API facade) does `dynamic_cast<LlamaCppBackend*>` to reach `llama_model_ptr()`/`llama_context_ptr()` for LoRA adapter load/unload/swap — meaning the facade knows about the concrete llama.cpp-backed class, not just the abstract `IInferenceBackend` interface.
4. **`src/inference/interface_factory.cpp`** also downcasts to `LlamaCppBackend` specifically to call `common_chat_parse_reliable()`/`parse_response()`, routing around the generic interface for llama.cpp's `common_chat` parsing.
5. **Global process state**: `src/inference/inference_c_api.cpp` manages a process-global `llama_log_set` redirect/silence mechanism (ggml logging), since llama.cpp exposes only a single-slot global log callback — entropic has to build its own mutex-guarded wrapper around that global to make it safe.
6. **Config surface**: `include/entropic/types/config.h` mirrors a large number of llama.cpp's own tunables nearly 1:1 (`n_ubatch`, `split_mode`, `main_gpu`, `offload_kqv`, `rope_freq_base/scale`, `n_seq_max`, penalty-sampler knobs) — these are explicitly documented as "llama.cpp pass-through fields."
7. **Documented behavioral coupling to the exact pinned commit**: `speculative_compat.h` explicitly says it duplicates logic from `extern/llama.cpp/common/speculative.cpp`'s file-private helper because that check isn't exposed via the public API — i.e., entropic reimplements internal (non-exported) llama.cpp logic to stay compatible with speculative decoding, and calls out that this is tied to the pinned commit.
8. Even file-format identity leaks through: `entropic.h` documents its context-save blob as "bit-for-bit the llama.cpp `llama_state_get_data` output... not portable across llama.cpp commits."

So the dependency isn't just "link against libllama.a" — it's vendored source, built inline into the shared library, with llama.cpp's C types appearing in entropic's own public interface headers, its concrete backend class downcast to from the top-level facade and factory, its process-global logging semantics wrapped by hand, and at least one piece of llama.cpp's *internal* (non-public-API) logic reimplemented in entropic to track a specific pinned commit.
