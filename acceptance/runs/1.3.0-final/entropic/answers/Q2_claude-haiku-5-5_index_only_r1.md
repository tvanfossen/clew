**How it's brought in:** llama.cpp is a git submodule, pinned to commit **b8420**, and linked directly into the inference library. There is no wrapper package. `docs/roadmap.md` (v1.8.0) records the decision: "llama.cpp as git submodule (direct linkage, no wrapper)". The pin is stated in the file header of `src/inference/llama_cpp_backend.cpp`. The index does not contain the CMake wiring itself (no `CMakeLists.txt` symbols or submodule config are queryable), so how the submodule is added and linked is something I can't confirm from here. Read the root `CMakeLists.txt` and `.gitmodules` for that.

**How far it reaches into entropic's source:** narrowly, and only in the inference layer.

- **Direct llama.cpp users (7 files in `src/inference/`):**
  - `llama_cpp_backend.{h,cpp}`: the main consumer. It calls the C API directly (`llama_model_load_from_file`, `llama_init_from_model`, `llama_decode`, `llama_sampler_chain`, `llama_chat_apply_template`, per its file doc). It also covers multi-sequence batching, speculative decoding, MTP heads, and multimodal (mtmd).
  - `llama_cpp_sampler.{h,cpp}`: wraps a `llama_sampler` chain.
  - `llama_cpp_tokenizer.{h,cpp}`: wraps `llama_vocab` and tokenize/detokenize.
- **One outside touchpoint:** `inference_c_api.cpp` (`entropic_create_inference_backend`) constructs `LlamaCppBackend`. That is the only place the rest of the engine reaches the llama-backed class.
- **Not in the public surface:** the header doc says the backend is "internal to inference .so, not exposed across boundaries." Design rule 1 and the "no third-party headers in interface contracts" standard keep llama types out of `include/entropic/`. I found no llama symbols under `include/`, `python/` or `examples/`.
- **Tests:** several unit tests (`tests/unit/inference/adapter_manager_test.cpp`, `speculative_compat_test.cpp`, `vocab_only_smoke_test.cpp`) define mock `llama_*` functions and override them at link time. The model tests in `tests/model/` exercise the real library.

**Summary:** the dependency is a pinned submodule linked straight into the inference library. Its use is confined to the seven `src/inference/llama_cpp_*` files plus the one factory call in `inference_c_api.cpp`. It does not appear in the public headers, the Python wrapper, or the examples.