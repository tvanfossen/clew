**Why it calls twice.** `LlamaCppTokenizer::tokenize` (`src/inference/llama_cpp_tokenizer.cpp:55-63`) uses llama.cpp's two-phase sizing protocol. The first `llama_tokenize` call passes a null buffer and zero capacity. llama.cpp answers with the negative of the required token count, and the code flips the sign to get the size. The second call fills a vector of that size. The first call is a size query, not an attempt that failed. Nothing is retried.

The same two-step shape appears in `detokenize` (lines 93-104). It tries a fixed 256-byte stack buffer, and only if llama.cpp returns a negative size does it allocate exactly that size and call again. That is the closest thing to a retry in the file, but it is still a buffer-size fallback, not a retry of a failed operation. A test helper in `tests/model/test_gh87_common_chat_e2e.cpp:51-58` copies the tokenize probe-then-fill pattern.

So I would not call it retry logic. It is size negotiation. There is no loop, no attempt limit beyond two, and no backoff. A failure in the probe is not handled at all: the code treats the negative value as a size and goes straight to the fill.

**What the caller receives on failure.** `tokenize` returns an empty `std::vector<int32_t>`. It does this in three cases: the vocab pointer is null (silent), the fill call returns negative (logged at error level, with only the text length), or no tokenizer is wired (`llama_cpp_backend.cpp:795`). The interface contract at `include/entropic/inference/tokenizer.h` says "empty on failure or empty input", so a failure cannot be told apart from an empty prompt. `detokenize` similarly returns `""` on failure.

**What the callers do with the empty result:**

| Caller | Behaviour on empty tokens |
|---|---|
| `do_count_tokens` / `count_tokens` (`llama_cpp_backend.cpp:825`) | Returns `0`. The C API `entropic_inference_count_tokens` (`inference_c_api.cpp:548`) returns that `0` too. Its doc says "text_len/4 estimate on error", but the estimate only happens on a caught exception, so this doc does not match the code. |
| `tokenize_text` (`:837`) | Passes the empty vector through. |
| `do_generate_text_only`, `do_generate_cancellable`, `do_generate_streaming` (`:2561`, `:2643`, `:2728`) | No check. They log "0 input tokens" and call `run_prefill_cached`. `run_prefill` (`:1484`) with zero tokens clears KV memory and returns true, so generation proceeds with no prompt in context. The sampling path was not traced, so I can't say whether it errors or emits junk. The log line is the only visible trace. |
| `do_complete` (`:3947`) | No check. Same path into `decode_loop`. |
| `do_generate_batch` (`:1911`) | Stores empty token vectors and computes prefix/suffix lengths without validation. I did not trace what the batched decode does with them. |
| System-prefix sizing (`:2066`) | Returns `0`, which reads as "no system prefix". |
| Speculative (`:3593`) and MTP (`:3921`) | The only callers that guard. They reject with `GENERATE_FAILED` when `tokens.size() < 2`. |

Detokenize failures return `""`, which the streaming loop (`:1534`) and content concatenation (`:1819`) append as nothing, so a bad token is dropped silently.

**Bottom line.** The double call is a size-probe protocol, not a retry. A tokenization failure is reported only as an empty vector, which most generation entry points do not check. The result is that a failed encode can surface as a generation from an empty context, or as a count of `0`, with only an error-level log in the fill-failure branch. The cleanest fix is to return a status (or `std::optional`) from the Tokenizer seam and have the generate, complete and count entry points return an error code on failure. Changing the `Tokenizer` seam signature is an interface change under the repo's rules, so it needs user sign-off.