**How it's brought in**

llama.cpp is a git submodule at `extern/llama.cpp` (`.gitmodules`, pointing at `ggml-org/llama.cpp`). It is not fetched with FetchContent like spdlog, ryml, Catch2, json and httplib in `extern/CMakeLists.txt`. Those are fetched at configure time, while llama.cpp is built from the checked-out tree.

`extern/CMakeLists.txt` configures it and pulls it in with `add_subdirectory`:

- Upstream examples, server, tests and tools are switched off. `LLAMA_BUILD_COMMON` is forced on, since mtmd needs the `common` target.
- CUDA is bridged from `ENTROPIC_HAS_CUDA` to `GGML_CUDA`.
- `add_subdirectory(llama.cpp EXCLUDE_FROM_ALL)` builds the core library, and `llama.cpp/tools/mtmd` is added separately for multimodal support.
- The build is static, and the comment says consumers never link to llama directly.

Two comments in that file are stale. The header says llama.cpp is "NOT built in v1.8.0", and the pin is described as b8420. The submodule is at `20a04b22`, and the other comments cite different pins. Treat the commit in `git submodule status` as the real pin.

**How far it reaches into entropic's source**

It reaches in deep, but it is contained in one layer.

1. **Inside `src/inference/`**, llama.cpp is used directly. Files that include `llama.h`, `common.h`, `chat.h`, `sampling.h` or `mtmd.h` are `llama_cpp_backend.{h,cpp}`, `llama_cpp_sampler.{h,cpp}`, `llama_cpp_tokenizer.{h,cpp}`, `orchestrator.cpp`, `adapter_manager.cpp`, `speculative_compat.cpp`, `grammar_registry.cpp`, and `tool_call_markers.h`. The backend is the main consumer of the C API and of `common_chat`, `common_speculative` and `mtmd` helpers.

2. **Outside `src/inference/`**, there are few direct references, and none of the core or config sources include a llama header:
   - `src/facade/entropic.cpp` includes `llama_cpp_backend.h`, so llama types reach the facade implementation. It calls `llama_model_ptr()` and `llama_context_ptr()` for adapter load, unload and swap.
   - `src/config/loader.cpp` only parses the `ggml_logging` and `llama_log_path` config keys.
   - `src/core/response_generator.cpp` and `src/core/engine.cpp` mention llama.cpp only in comments.

3. **Public headers under `include/entropic/`** never include llama.h. They use forward declarations such as `struct llama_model;`, `struct llama_context;` and `struct llama_adapter_lora;` in `orchestrator.h`, `adapter_manager.h` and `speculative_compat.h`. These are opaque pointer types, so the llama.cpp ABI is not exposed by value. The C API in `entropic.h` only mentions llama.cpp in documentation.

4. **Link and include wiring** in `src/inference/CMakeLists.txt` and `src/facade/CMakeLists.txt`:
   - The inference object library links `llama-common` publicly and `llama` and `mtmd` privately.
   - The facade absorbs `llama`, `mtmd` and `llama-common` as `LINK_ONLY` into `librentropic.so`.
   - The facade also adds `extern/llama.cpp/include` and `ggml/include` to its include path.
   - The installed `entropic-config.cmake.in` says llama.cpp is absorbed and consumers need no `find_dependency`.

**Summary:** the dependency enters through the submodule and `extern/CMakeLists.txt`, is statically absorbed into `librentropic.so`, and is consumed in `src/inference/`. Its types surface only as forward-declared opaque pointers in public headers and as direct use in the facade's `.cpp`. Consumers of the installed package never see the llama.cpp headers.

I got this from the index and from grep over the source. I did not build the project, so the link-level claims rest on the CMake files and not on a configured build.