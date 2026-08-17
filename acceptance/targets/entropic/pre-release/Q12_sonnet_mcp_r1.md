# Q12 — mcp — sonnet — run 1

## Where the boundary is

Entropic vendors llama.cpp as a git submodule at `extern/llama.cpp` (`.gitmodules`), pinned to commit `20a04b22063020cd0f29b7781f5352d7a6abf786` (tag `gguf-v0.19.0-840-g20a04b220`) — code comments refer to this pin by its short form **"b8420"** (`src/inference/llama_cpp_backend.cpp:6`, `src/inference/adapter_manager.cpp:6`, `src/inference/llama_cpp_backend.h:8`).

Entropic's own abstraction seam is a set of pure-virtual interfaces:
- `entropic::InferenceBackend` — concrete base with 80% shared logic (`include/entropic/inference/backend.h:69`)
- `entropic::Tokenizer` (`include/entropic/inference/tokenizer.h:40`)
- `entropic::Sampler` / `entropic::SamplerFactory` (`include/entropic/inference/sampler.h:48,93`)

The **only** production implementations of these interfaces that talk to llama.cpp are:
- `entropic::LlamaCppBackend` (`src/inference/llama_cpp_backend.h:65`, brief calls itself "the 15% layer")
- `entropic::LlamaCppTokenizer` (`src/inference/llama_cpp_tokenizer.h:35`)
- `entropic::LlamaCppSamplerFactory` / `entropic::LlamaCppSampler` (`src/inference/llama_cpp_sampler.h:118,~120`)

(Their only siblings in the index's `derived` lists are test mocks — `MockBackend`, `MockTokenizer`, `MockSampler`, `MockSamplerFactory` — confirming these are the sole real seams.)

## How wide the boundary actually is

It's wider than "one backend class." Seven first-party translation units under `src/inference/` `#include <llama.h>` (or `mtmd.h`/`ggml.h`) directly and call the C API:

| file | lines | llama.cpp surface used |
|---|---|---|
| `src/inference/llama_cpp_backend.h` / `.cpp` | 1281 / 4125 | `llama_model`, `llama_context`, `llama_vocab`, `llama_token`/`llama_seq_id`, decode loop, batching, MTP draft — plus `mtmd_context`/`mtmd_bitmap` (multimodal), forward-declared at `llama_cpp_backend.h:50-51`, full types only in the `.cpp` |
| `src/inference/llama_cpp_tokenizer.cpp`/`.h` | 107 / 53 | vocab tokenize/detokenize API |
| `src/inference/llama_cpp_sampler.cpp`/`.h` | 227 / 137 | `llama_sampler*` chain |
| `src/inference/adapter_manager.cpp` | 495 | `llama_adapter_lora_init`/`_free` (LoRA C API, explicitly "pinned b8420" at line 6) |
| `src/inference/speculative_compat.cpp` | 277 | `llama_model_is_recurrent`/`llama_model_is_hybrid` (`:58,:64`) — this file's entire purpose is bridging llama.cpp model-type differences |
| `src/inference/grammar_registry.cpp` | 297 | `llama_sampler_init_grammar`/`llama_sampler_free` (`:264,:271`) |

`src/inference/orchestrator.cpp` (1832 lines) includes `llama_cpp_backend.h` and `dynamic_cast`s to `LlamaCppBackend*` (`:330,:394,:396`) but doesn't call llama.h symbols itself — it depends on the concrete class, not the library.

**The boundary leaks past `src/inference/` into public headers**, though only as opaque pointer types (not full API usage): `include/entropic/inference/adapter_manager.h:37-39`, `orchestrator.h:44-45`, and `speculative_compat.h:47` forward-declare `struct llama_model`, `llama_context`, `llama_adapter_lora` so entropic's own public API surface carries llama.cpp's pointer types as opaque handles. `include/entropic/types/config.h` also encodes llama.cpp semantics (its `llama_split_mode` enum at `:178`, hybrid/recurrent detection at `:886`, `llama_log_path` field at `:985`) even though it doesn't include `llama.h`.

Build-level coupling: `src/facade/CMakeLists.txt:40,48,67-69` links `llama`/`llama-common` and adds `extern/llama.cpp/include` and `extern/llama.cpp/ggml/include` to the include path.

Scale: `extern/llama.cpp` indexes to 1237 files / 30077 symbols vs. entropic's own `src`+`include` at 201 files / ~2783 symbols — the vendored library is roughly 10× the symbol count of entropic's first-party inference code, but only **7 files** of those 201 actually call into it.

## What would break on an upgrade

Directly, in likely-impact order:
1. **`src/inference/llama_cpp_backend.{h,cpp}`** — largest and deepest coupling (decode loop, batching, MTP, mmproj/vision via mtmd). Any llama.cpp API rename/signature change here is highest risk.
2. **`src/inference/speculative_compat.cpp`** — is *literally* the API-compatibility shim; if llama.cpp changes model-type detection semantics this is the first thing that needs editing (and the class is explicitly named for a pinned commit — `LlamaCppBackend_b8420`, `llama_cpp_backend.h:6-8` — implying the versioned-subclass pattern is the intended upgrade mechanism, not in-place editing).
3. **`src/inference/adapter_manager.cpp`** — LoRA C API, explicitly commented as pinned to b8420.
4. **`src/inference/grammar_registry.cpp`** — grammar sampler init/free.
5. **`src/inference/llama_cpp_tokenizer.cpp`** / **`llama_cpp_sampler.cpp`** — narrower, single-purpose adapters, lower risk but still direct API surface.
6. **`src/facade/CMakeLists.txt`** — link/include paths would need touching for any llama.cpp target rename or restructure.
7. **Public headers with forward-declared llama types** (`include/entropic/inference/adapter_manager.h`, `orchestrator.h`, `speculative_compat.h`) — only break if llama.cpp renames these structs, but that would ripple into entropic's own public API, not just implementation files.

**What would not break**: `src/inference/orchestrator.cpp` (depends on `LlamaCppBackend`, not llama.cpp directly), `src/config/loader.cpp:657` and `src/core/response_generator.cpp:205,354` (mention "llama" only in comments/a config key name, no API calls), and the `InferenceBackend`/`Tokenizer`/`Sampler`/`SamplerFactory` interfaces themselves, which are llama.cpp-agnostic by design.

## Gaps

- I did not read the full 4125-line `llama_cpp_backend.cpp` body — the dossier/grep confirm which llama.cpp symbols it touches by name, but I did not verify each call site individually for version-sensitivity.
- I have not diffed against a newer llama.cpp commit, so "what would break" is inferred from *which* API surfaces are touched (decode, sampler, vocab, LoRA, grammar, model-type queries, mtmd) rather than confirmed against an actual upstream diff — I have no such diff available in this environment.
- Whether `include/entropic/types/config.h`'s `llama_split_mode`-shaped enum and hybrid/recurrent config knobs are kept in sync with llama.cpp by a test or only by convention was not checked.
