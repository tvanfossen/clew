**Short answer:** llama.cpp is a git submodule at `extern/llama.cpp`, pinned to a commit. Its C and common-library APIs are called from the `src/inference/` layer and nowhere else. The public `include/entropic/` headers mention it only in comments. Caveat: the index doesn't cover CMake files, so I could not confirm how the submodule is built into the library. Everything below is from doc and source comments plus symbol bodies.

**How it's brought in**

- `docs/architecture-cpp.md` (Project Structure) lists `extern/llama.cpp/` as a git submodule.
- The pin is a commit, and the pin history is in `RELEASE_NOTES.md`: `253ba110b` (v2.1.11), then `ac4cddeb` (v2.9.0), then `20a04b22` / `b9886` (v2.9.3).
- `src/inference/llama_cpp_backend.cpp:1` still says "Pinned against llama.cpp submodule b8420". That comment is stale, since the pin has moved on.
- Vendoring rules: `CONTRIBUTING.md` says vendored deps go under `extern/`.
- Other third-party code is pulled differently. `examples/openai-server/README.md` says cpp-httplib and nlohmann/json come in via CMake `FetchContent`. The core engine's deps (sqlite, spdlog, ryml, nlohmann/json) are listed in the architecture doc's dependency graph.

**How far it reaches into entropic's source**

| Layer | Files | What it touches |
|---|---|---|
| Backend | `llama_cpp_backend.{h,cpp}` | Model load/unload, context creation, decode loop, KV state save/restore, prompt cache, logprobs, speculative and MTP decode. `LlamaCppBackend` is a concrete subclass of `InferenceBackend`, with `do_*` overrides. Its members are raw `llama_model*`, `llama_context*` and `llama_vocab*`. |
| Sampler | `llama_cpp_sampler.{h,cpp}` | Wraps a `llama_sampler` chain. `LlamaCppSampler` takes ownership of the chain. |
| Tokenizer | `llama_cpp_tokenizer.{h,cpp}` | Forwards to `llama_tokenize` / `llama_token_to_piece` against a borrowed `llama_vocab*`. |
| Chat / tool parsing | `adapters/adapter_registry.cpp`, `tool_call_markers.h`, `llama_cpp_backend.h` (`render_with_tools`, `parse_response`) | Uses llama.cpp's `common_chat` render and PEG parsers. Entropic decides when to trust them: only dedicated grammars such as PEG_GEMMA4 parse multi-parameter tool calls. Tool-call close markers are pinned to vendored `chat-peg-parser.cpp` defaults. |
| Speculative decoding | `speculative_compat.{h,cpp}` | Mirrors the file-private `common_speculative_are_compatible` from `extern/llama.cpp/common/speculative.cpp`, because the upstream version is not exported. |
| LoRA | `adapter_manager.cpp` | Calls the llama.cpp LoRA C API (`llama_adapter_lora_init`, `llama_set_adapters_lora`). |
| Images | `image_preprocessor.cpp` | Uses the `stb_image` copy vendored with llama.cpp. Resize is in-house because `stb_image_resize2` isn't in that tree. |
| Logging | `OLD_NOTES.md` | Routes the llama log callback into entropic's log files. |
| Tests | `tests/unit/inference/*` | Use link-time mocks for llama adapter functions. Seams `Tokenizer` and `Sampler` exist so most backend logic can be tested without a model. |

**Where it stops**

- The seam design is meant to stop llama.cpp at the backend. `include/entropic/inference/tokenizer.h` and `sampler.h` are abstract interfaces, and their briefs describe llama.cpp only as history.
- `architecture-cpp.md` requires pure C at `.so` boundaries with no third-party headers in interface contracts. The index found no llama types in `include/entropic/interfaces/`.
- I did not read the signatures of every public header, so "no llama types leak" is supported by the rule and the index's search results, not verified header by header.