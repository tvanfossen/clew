I have enough to answer confidently from the index.

## How the dependency is brought in

llama.cpp is vendored as a **pinned git submodule**, currently at commit `b8420`. That's stated directly in the file-level doxygen for `src/inference/llama_cpp_backend.cpp`: *"Pinned against llama.cpp submodule b8420"*, and repeated in `src/inference/adapter_manager.cpp`'s file doc: *"Integrates with llama.cpp LoRA C API (pinned b8420)"*. This is exactly the "decl only, no repo shape" limit of the index worth flagging: the index has no submodule/build-system layer, so I can't show you the `.gitmodules` entry, the CMake `add_subdirectory`/`FetchContent` wiring, or which vendored path it lives under — that's outside what `search`/`dossier` cover (files corpus returned zero hits for `llama*`, meaning no llama.cpp source itself is indexed as first-party — it's genuinely external/vendored, consistent with the "external is a git tree" convention this repo follows). If you need the exact CMake incantation, that's a source-reading task, not an index one.

## How far it reaches into entropic's own source

The dependency is deliberately walled off behind entropic's own abstract interfaces, and only a small, named set of concrete "seam" files touch the llama.cpp C API directly:

- **`src/inference/llama_cpp_backend.{h,cpp}`** — `entropic::LlamaCppBackend`, described as the "common llama.cpp patterns (15% layer)" subclass of the abstract `InferenceBackend`. This is the deepest integration point: it holds raw `llama_model*`, `llama_context*`, `llama_vocab*`, `llama_token`/`llama_seq_id` state directly as member variables (`model_`, `ctx_`, `vocab_`, `mtp_draft_model_`, `mtp_draft_ctx_`, etc.), and calls straight into `llama_model_load_from_file()`, `llama_init_from_model()`, plus batched-decode, KV-cache, speculative-decode (MTP draft model) and multimodal (`mtmd_context`) logic. This is the biggest chunk of direct exposure.
- **`src/inference/llama_cpp_sampler.{h,cpp}`** — `LlamaCppSampler`/`LlamaCppSamplerFactory`, a concrete adapter wrapping a `llama_sampler*` chain behind the abstract `Sampler`/`SamplerFactory` interfaces.
- **`src/inference/llama_cpp_tokenizer.{h,cpp}`** — `LlamaCppTokenizer`, forwarding to `llama_tokenize`/`llama_token_to_piece` against a borrowed `llama_vocab*`, behind the abstract `Tokenizer` interface. Its own file doc notes it's excluded from the CPU-only unit-test gate "by design — its only job is to be a [thin adapter]."
- **`src/inference/adapter_manager.cpp`** — LoRA lifecycle, calling `llama_adapter_lora_init()` / `llama_set_adapters_lora()` / `llama_adapter_lora_free()` directly. The header `include/entropic/inference/adapter_manager.h` stays llama-agnostic in its public contract.
- **`include/entropic/types/config.h`** — one config field, `llama_log_path`, an override path for ggml/llama logging (gh#23). Naming leaks in, but no API usage.

Everything else — `InferenceBackend`, `Sampler`, `SamplerFactory`, `Tokenizer` interfaces, and the orchestrator's `adapter_manager()` accessor — stays on entropic's own abstract types. Tests confirm the boundary is intentional: `tests/unit/inference/adapter_manager_test.cpp` mocks `llama_adapter_lora_init/free` and `llama_set_adapters_lora` via **link-time substitution** rather than linking real llama.cpp, precisely because "the real llama.cpp adapter API is not available in unit tests (no GPU, no model)."

So: one submodule pinned at a specific commit, and exactly four `src/inference/` seam files (plus one config field) are where the C API is actually named and called — everything upstream of those consumes entropic's own `InferenceBackend`/`Sampler`/`Tokenizer` abstractions and never sees a `llama_*` symbol.
