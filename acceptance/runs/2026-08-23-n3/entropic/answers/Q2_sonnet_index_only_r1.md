I have enough to answer.

## How llama.cpp is brought in

The index itself can't show a vendoring mechanism (no `CMakeLists.txt`/build-script parsing, and no external git tree shows up under `src/inference` or anywhere else with `external_files > 0`) — so I can't point you at a `FetchContent`/submodule declaration directly from the graph. What the index *can* confirm is the file-level doxygen comment on `src/inference/llama_cpp_backend.cpp`, which states explicitly:

> "Pinned against **llama.cpp submodule b8420**."

So per the repo's own documentation, llama.cpp is vendored as a **git submodule pinned to a specific upstream commit (`b8420`)**, not fetched dynamically or built from a loose copy. The index doesn't see that submodule's contents at all (it's a separate git tree, and no such tree shows up anywhere in the file inventory), which is consistent with a submodule that either isn't checked out in this indexed copy or is deliberately excluded from indexing scope — I can't tell which from here; that's a genuine gap, not something to guess past.

## How far it reaches into entropic's own source

The dependency is deliberately walled off, architecturally consistent with the repo's "pure C at `.so` boundaries" rule:

- **Concentrated almost entirely in `src/inference/`**, specifically:
  - `llama_cpp_backend.h`/`.cpp` — the big one (134 + 78 symbols), implementing `entropic::LlamaCppBackend`, which subclasses `InferenceBackend` and holds raw llama.cpp handles directly as members: `llama_model* model_`, `llama_context* ctx_`, `const llama_vocab* vocab_`, plus `mtmd_context* mtmd_ctx_` for the multimodal (libmtmd) path and MTP draft-model members.
  - `llama_cpp_tokenizer.h`/`.cpp` — a thin seam forwarding to `llama_tokenize`/`llama_token_to_piece`.
  - `llama_cpp_sampler.h`/`.cpp` — sampler chain built on llama.cpp's sampling API.
  - `speculative_compat.cpp` and its test — checks `llama_model_is_hybrid`/`llama_model_is_recurrent` for speculative-decoding compatibility.

- **One deliberate crack in the wall**: `src/inference/orchestrator.cpp`'s `resolve_target_model()` does a `dynamic_cast<LlamaCppBackend*>` on a generic `InferenceBackend` pointer and calls `llama_model_ptr()` to get a raw `llama_model*` for speculative-pair resolution (`resolve_speculative_pair` in `include/entropic/inference/orchestrator.h`). That's the one place outside the `LlamaCppBackend` family that reaches through the abstraction to touch a llama.cpp type by name, rather than going through the `InferenceBackend` interface.
- Everything else in the codebase (orchestrator logic in general, adapters, prompt cache, the C API surface in `inference_c_api.cpp`) interacts through entropic's own `InferenceBackend`/`GenerationResult`/`ModelConfig` types — no other raw `llama_*`/`mtmd_*` symbols surfaced in a symbol search outside the inference backend files and their tests.

**Bottom line:** llama.cpp is pulled in as a pinned git submodule (per the file doc; the index has no visibility into the submodule mechanics themselves), and its API penetrates entropic's source almost exclusively through `LlamaCppBackend` and its two supporting seam files (tokenizer, sampler) in `src/inference/`. The one exception is `orchestrator.cpp::resolve_target_model`, which downcasts through the backend interface to grab a raw `llama_model*` for speculative decoding — a narrow, named leak rather than broad exposure.
