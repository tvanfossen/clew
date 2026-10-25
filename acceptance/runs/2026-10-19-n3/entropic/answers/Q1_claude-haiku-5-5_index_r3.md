**Why it calls twice:** Both calls are in `LlamaCppTokenizer::tokenize` (`src/inference/llama_cpp_tokenizer.cpp:55` and `:61`). The first passes a null buffer with size 0 to ask llama.cpp how many tokens the text needs. llama.cpp returns the count as a negative number, which line 58 flips to positive. The second call passes a vector of that size and does the real encode. So it is a two-pass size query, the usual llama.cpp C API pattern.

**Is it retry logic?** No. Nothing is retried and there is no loop. The first call never fails in the sense of "try again"; its only job is to size the buffer. The code's own comment calls it "the sized retry" (`llama_cpp_tokenizer.cpp:44-45`), which is misleading.

The closer case is `detokenize` (`llama_cpp_tokenizer.cpp:93-101`). It tries a 256-byte stack buffer and, when llama.cpp reports the buffer is too small, retries once with the exact size. That one is a real retry, though still a single retry with no loop and no error recovery.

**What the caller receives on failure:** If the second call returns a negative value, the code logs an error (with the text length only) and returns an empty `std::vector<int32_t>`. There is no error code, exception, or status. An empty vector is also what a legitimately empty input produces, and `LlamaCppBackend::tokenize` returns the same empty vector when no tokenizer is wired (`llama_cpp_backend.cpp:796`). So the caller cannot distinguish "no tokenizer," "tokenize failed," and "empty input."

**What callers do with it:**

| Caller | What happens on empty |
|---|---|
| `do_count_tokens` (`llama_cpp_backend.cpp:825`) | Returns 0 |
| `entropic_inference_count_tokens` (`inference_c_api.cpp:548`) | Returns 0 to the C consumer. The `len/4` fallback in its `catch` never runs because nothing throws. |
| `tokenize_text` (`llama_cpp_backend.cpp:837`) | Returns empty |
| `do_complete` (`:3947`) | Logs "0 input tokens", then goes straight into `decode_loop` |
| `do_generate_text_only` (`:2561`) | Goes into `run_prefill_cached` with no check |
| `compute_prefix_token_count` (`:2051`) | Returns 0 prefix tokens, which then feeds the prompt cache |
| Batch path (`:1911`) | Stores the empty vector per request without a check |

For the generate and complete paths, nothing checks for emptiness before prefill. `run_prefill` with zero tokens clears the KV memory, loops zero times, and returns true (`llama_cpp_backend.cpp:1484-1503`). The sampler then runs on whatever state the context holds. I did not trace what that produces. It may yield garbage output or a decode error later, and it is the most important thing to verify with a real run. The other rows I checked by reading the code, and I did not read the remaining `tokenize` call sites (lines 2643, 2728, 3593, 3921) in full.

In short, a tokenizer failure is silent at the seam. It gets converted into "zero tokens," which callers treat as valid input. The only trace is one error log line. A status return or an error code on `tokenize` would fix this, and it would need an interface change if `Tokenizer` is part of the immutable `i_*.h` contract.