**Short answer:** llama.cpp enters the build as a git submodule and is linked directly into the inference library. Its C API is used from one directory, `src/inference/`, and does not appear in entropic's public headers.

**How it's brought in**

- `extern/llama.cpp` is a git submodule. `extern/CMakeLists.txt` says it is "NOT built in v1.8.0", and the architecture doc lists it as a "Submodule" with "Direct C API" (`docs/architecture-cpp.md`, External Dependencies).
- `src/inference/CMakeLists.txt` links it. Per the architecture doc, the `librentropic-inference-{cuda,vulkan,cpu}.so` variants link `llama.cpp` and implement `IInferenceBackend`. So llama.cpp is a compile-time backend variant, not a runtime plugin.
- The index does not show the CMake link lines, so I can't confirm the exact target wiring.

**How far it reaches**

| Layer | Files | Uses llama.cpp? |
|---|---|---|
| Public C API / `include/entropic/` | interfaces, types, `entropic.h` | No llama types found. The one match is `llama_log_path`, a config variable name in `types/config.h`. |
| Abstract interfaces | `IInferenceBackend`, `Sampler`, `Tokenizer` | No |
| Concrete backend | `src/inference/llama_cpp_backend.{h,cpp}` (`LlamaCppBackend`) | Yes: model load, context, `llama_decode`, batching, chat templates, speculative and MTP decode, state save/restore, mtmd vision |
| Sampler / tokenizer adapters | `llama_cpp_sampler.{h,cpp}`, `llama_cpp_tokenizer.{h,cpp}` | Yes: wrap `llama_sampler` chains and `llama_vocab` |
| Image decode | `image_preprocessor.cpp` | Not llama.cpp itself. It uses the `stb_image` copy vendored with llama.cpp. |
| Tests | `tests/unit/inference/*` | Mock the llama functions by link-time substitution, so unit tests don't link the real library. |

So the dependency is contained: `LlamaCppBackend` is the one class that owns llama.cpp state, and the sampler and tokenizer adapters are its satellites. Everything above it talks to the abstract interfaces. The architecture rules (pure C at `.so` boundaries, no C++ ABI crossing, no third-party headers in interface contracts) are what keep llama.cpp types from leaking out, and the index shows nothing that breaks them.

**Caveats**

- The index records symbols, not `#include` edges. "Only `src/inference/` uses it" is inferred from symbol and name matches, and I did not confirm every includer of `llama.h`. There is a root-level `llama.h` file in the index with no symbols and no harvested docs, which I could not interpret.
- The docs disagree about the pin. `llama_cpp_backend.cpp` and its header say "pinned against b8420" (a v1.8.x-era comment). `RELEASE_NOTES.md` records a bump to b9592 (`extern/llama.cpp` `253ba110b → ac4cddeb`), and the speculative-decode comment cites `253ba110b`. The current pin should be checked against the submodule itself.
- The header describes a "versioned subclass pattern" with a `LlamaCppBackend_b8420` subclass for the pinned commit. No such symbol exists in the index. The only concrete class is `LlamaCppBackend`, so that comment is stale.