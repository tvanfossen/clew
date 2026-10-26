**How it's brought in:** llama.cpp is a git submodule at `extern/llama.cpp`, pinned to a specific commit. `docs/architecture-cpp.md` lists `extern/llama.cpp/` as a git submodule in the project structure. `docs/architecture-cpp.md` also says llama.cpp is linked directly and is not a plugin boundary. The index doesn't contain the CMake files, so I can't confirm the exact link mechanics (static vs. shared, target names).

**The pin:** Bumps are recorded in `RELEASE_NOTES.md`, for example `253ba110b → ac4cddeb` and later bumps in v2.9.3 and v2.9.4. The docs disagree on the current pin. `src/inference/llama_cpp_backend.cpp`'s file comment says "pinned against llama.cpp submodule b8420", while the architecture doc and release notes use commit hashes. The file comment looks stale, but I can't verify which pin is live from the index.

**How far it reaches into entropic:**

| Layer | Reach |
|---|---|
| `src/inference/` | Heavy. `LlamaCppBackend`, `LlamaCppSampler` / `LlamaCppSamplerFactory`, `LlamaCppTokenizer` call the llama.cpp C API directly. `speculative_compat`, `mtp_envelope`, `tool_call_markers` and `image_preprocessor` also depend on llama.cpp internals or its behavior. |
| `include/entropic/interfaces/` | None by design. Architecture rule: no third-party headers in interface contracts. The engine talks to the abstract `InferenceBackend`, `Sampler`, `SamplerFactory` and `Tokenizer`. |
| Public C++ class `LlamaCppBackend` | Leaks llama types. `llama_model_ptr()` and `llama_context_ptr()` return raw `llama_model*` / `llama_context*`, and `CommonChatResult` wraps llama.cpp's `common_chat` parser output. |
| `tests/` | Mocks and fakes some llama.cpp symbols, such as `llama_adapter_lora_init` and `llama_set_adapters_lora` in `adapter_manager_test.cpp`. Also has model tests that run against real models. |
| Docs and comments | Several files hard-code assumptions about specific upstream code. `tool_call_markers.h` tracks `common/chat-peg-parser.cpp` `section_end` defaults. `mtp_envelope.h` depends on `draft()` reading `data[0]`. `speculative_compat.cpp` mirrors a file-private function from `common/speculative.cpp`. The docs say these need re-checking on every pin bump. |

**Limits of this answer:** The index holds only entropic's own source. `llama_model_load_from_file` and `common_chat_parse` return no dossier, so I can't see llama.cpp's internals or how its symbols connect to entropic's. Whether `entropic.h` (the C ABI) exposes any llama types is also outside what I could check; the design rules say it shouldn't. Reading `CMakeLists.txt` and `entropic.h` directly would settle the link mechanics and the C boundary.