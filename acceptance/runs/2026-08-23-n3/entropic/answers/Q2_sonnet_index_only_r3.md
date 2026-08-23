## How llama.cpp comes in

It's a **git submodule**, not a package dependency — `docs/architecture-cpp.md`'s Project Structure lists `extern/llama.cpp/` explicitly, and the roadmap entry for v1.8.0 ("C++ Project Scaffold") records the decision as **"llama.cpp as git submodule (direct linkage, no wrapper)"**. The architecture doc's External Dependencies table confirms the shape: `llama.cpp | Inference | Submodule | Linux/Mac/Win | Direct C API`. `src/inference/llama_cpp_backend.cpp`'s file doc pins it to a specific commit: **"submodule b8420."** This is deliberately not a vendored copy or a fetched prebuilt library — it's linked directly against llama.cpp's C API, and the build (`librentropic-inference-{cuda,vulkan,cpu}.so`) links llama.cpp straight into entropic's inference backend `.so`.

## How far it reaches into entropic's own source

Further than a single adapter file, though there is a real seam:

- **`entropic::LlamaCppBackend`** (`src/inference/llama_cpp_backend.h/.cpp`) is the core integration point, and llama.cpp's raw types leak directly into it as member state — `llama_model* model_`, `llama_context* ctx_`, `const llama_vocab* vocab_`, `llama_seq_id`, `llama_token`, plus a second model/context pair for MTP speculative drafting (`mtp_draft_model_`, `mtp_draft_ctx_`) and `::mtmd_context*`/`::mtmd_bitmap*` for multimodal. This is a large class — well over 100 methods/members in the dossier, spanning batched decode, KV-cache prefix save/restore, speculative decoding, tool-call parsing (`common_chat` from llama.cpp's `common/`), and multimodal prefill.
- **`LlamaCppSampler` / `LlamaCppSamplerFactory`** (`llama_cpp_sampler.h/.cpp`) wrap a raw `llama_sampler*` chain.
- **`LlamaCppTokenizer`** (`llama_cpp_tokenizer.h/.cpp`) forwards directly to `llama_tokenize`/`llama_token_to_piece` against a borrowed `llama_vocab*`.
- **`adapter_manager.cpp`** integrates with llama.cpp's LoRA API (`llama_adapter_lora_init/free`, `llama_set_adapters_lora`) for hot-swap lifecycle.
- **`image_preprocessor.cpp`** uses `stb_image`, which is vendored *inside* llama.cpp's own tree rather than entropic's.
- **`speculative_compat.h`** duplicates/extends one of llama.cpp's own static compatibility checks with an additional architecture gate.
- **`tool_call_markers_test.cpp`** is explicitly noted as "vendor-coupled to the common_chat PEG `section_end` defaults" at `extern/llama.cpp/common/chat-peg-parser`.

So the dependency isn't confined behind one opaque wrapper — llama.cpp's concrete types (`llama_model`, `llama_context`, `llama_vocab`, `llama_token`, `llama_seq_id`, `mtmd_context`) appear directly in entropic's own class members and signatures, consistent with the "direct linkage, no wrapper" design choice. The abstraction that *does* exist is at the interface level: entropic defines its own `Tokenizer`, `Sampler`/`SamplerFactory`, and `InferenceBackend` interfaces (in `include/entropic/inference/`), and the `LlamaCppBackend`/`LlamaCppSampler`/`LlamaCppTokenizer` trio are the sole concrete implementations of those interfaces (docs note these were pulled out as a "v2.3.10 seam impl" specifically so unit tests could inject mocks instead of needing the real llama.cpp API at link time — `llama_cpp_tokenizer.cpp`'s file doc says it's "uncovered by the CPU-only unit-test gate by design"). But that seam sits at the backend/sampler/tokenizer boundary — everything on the llama.cpp side of it, including LoRA adapters, multimodal preprocessing, and tool-call parsing, talks to llama.cpp's raw API and types directly.

The index can't tell me the CMake linkage details (how `extern/llama.cpp` is added as a subdirectory/target) since build scripts aren't parsed into the graph — that would need reading `CMakeLists.txt` directly.
