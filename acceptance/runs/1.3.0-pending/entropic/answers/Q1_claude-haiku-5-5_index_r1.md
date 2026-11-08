**Short answer:** the two calls are a size probe followed by the real call, both inside one function. That is not retry logic.

**The two calls.** Both are in `LlamaCppTokenizer::tokenize()` (`src/inference/llama_cpp_tokenizer.cpp:55` and `:61`). There is no second call site in another file; the grep found only these two `llama_tokenize` calls. The first passes a null buffer and size 0, so llama.cpp answers with the negated token count it would need. The code uses that to allocate the vector. The second call fills it. The probe always runs, even when nothing fails, which makes it a two-pass sizing idiom rather than a retry.

**Is it retry?** No. The second call is the only real attempt. If it returns a negative value, the function logs an error and returns `{}` immediately. Nothing loops and nothing tries again.

**What the caller receives on failure.** The failure value is an empty `std::vector<int32_t>`. That is also the correct result for empty input with `add_special=false`, so callers cannot tell the two apart. The error log records only the text length, not llama.cpp's return code.

**What the callers do with it**

| Entry point (`llama_cpp_backend.cpp` unless noted) | Receives | What happens |
|---|---|---|
| `entropic_inference_count_tokens` (`inference_c_api.cpp:558`) and `do_count_tokens` (`:825`) | `0` | Returned as a count of 0. The C API doc at `inference_c_api.cpp:544` says it returns a `text_len/4` estimate on error; the code only does that on a thrown exception, which a tokenizer failure does not produce. |
| `tokenize_text` (`:837`) | `{}` | Returned as empty IDs. |
| `do_generate_text_only` (`:2561`), the cancellable path (`:2643`), the streaming path (`:2728`) | `{}` | Logs "0 input tokens". `run_prefill_cached` runs on the empty list. `run_prefill` (`:1484`) clears the KV cache, decodes nothing, and returns `true`. Generation proceeds with no error code set. |
| `do_complete` (`:3947`) | `{}` | Same silent path, through `decode_loop` (only a prefill failure sets an error there). |
| `do_generate_batch` (`:1911`) | `{}` | Feeds the empty vector into the shared-prefix computation. I did not trace that further. |
| Speculative (`:3593`) and MTP (`:3921`) | `{}` | Guarded by `tokens.size() < 2`, which returns `ENTROPIC_ERROR_GENERATE_FAILED`. The error is caught, but its message says "prompt must have at least 2 tokens" when the real cause was a tokenizer failure. |
| `compute_prefix_token_count` (`:2066`) | `0` | Treated as a zero-length system prefix. |

**What this means.** On the plain generate and complete paths, a tokenizer failure does not surface as an error. The model generates from an empty prompt and reports success. The speculative and MTP paths do catch it, but with a misleading message. The C-level count API returns 0 where its docs promise an estimate.

**Caveats.** I read the code paths and did not run them, so the empty-prompt generation behavior is inferred from `run_prefill` and the decode loop. The tokenizer file is excluded from the CPU unit-test gate by design, and the unit tests use a mock tokenizer, so nothing in the unit suite exercises this failure on the real tokenizer.

**Possible fixes**, if you want them: change `tokenize` to return a status alongside the IDs (or `std::optional`), have the generate paths reject empty token input with an error code, and correct the `inference_c_api.cpp:544` doc or the behavior to match. I have not changed anything.