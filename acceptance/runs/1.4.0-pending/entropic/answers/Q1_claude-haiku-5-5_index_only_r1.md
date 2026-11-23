**Short answer:** the two `llama_tokenize` calls are a size probe followed by the real call, not retry logic. Also, both calls sit in the same function, not two places. The index shows only these two call sites, at `src/inference/llama_cpp_tokenizer.cpp:55` and `:61`, both inside `LlamaCppTokenizer::tokenize`.

**Why it calls twice**

llama.cpp's `llama_tokenize` returns a negative number when the output buffer is too small, and the magnitude is the required token count. The first call passes a null buffer with size 0 to learn that count. The code then allocates a vector of that size and makes the second call to fill it. The second call is the one that produces the result. Nothing is retried: there is no loop, no changed parameters, and no second attempt after a failure. The only "retry" wording in the index is a doc comment that calls it a "sized retry", which is misleading.

**Who calls into it**

`LlamaCppBackend::tokenize` (`llama_cpp_backend.cpp:788`) does not call llama.cpp directly. It forwards to the `Tokenizer` seam, and returns an empty vector if no tokenizer is wired. `tokenize_text` and `do_count_tokens` build on it.

**When tokenization fails**

- `LlamaCppTokenizer::tokenize` returns an empty vector and logs an error. The log includes only the text length, not the text.
- A null `vocab_` also returns empty, silently.
- An empty vector is the same value as a legitimate empty input, so the only failure signal is the log line.
- `do_count_tokens` converts that to a count of `0`.
- The C API `entropic_inference_count_tokens` returns that `0`. Its `len/4` fallback only fires on exceptions, and this path does not throw, so a failed count reads as zero tokens.

**What the callers do with the empty vector**

| Caller | Behaviour on empty |
|---|---|
| `do_complete` (`:3941`) | No check. Logs "0 input tokens" and calls `decode_loop`. `run_prefill` with zero tokens returns true without decoding. I did not read `generate_after_prefill`, so what it samples from is unverified. |
| `do_generate_batch` (`:1903`) | No check. An empty sequence forces the shared prefix to 0, then the code either takes the batch path or falls back to serial. I did not verify which. |
| `generate_mtp` (`:3906`) | The only caller that checks. A size under 2 returns `ENTROPIC_ERROR_GENERATE_FAILED` with "MTP prompt must have at least 2 tokens". A tokenizer failure is therefore reported as a prompt-length error. |
| `compute_prefix_token_count` (`:2051`) | Returns `0`, so the system-prefix size is silently treated as zero. |

The main issue is that failure is an empty vector, which callers cannot tell apart from empty input. Only `generate_mtp` checks for it, and it reports the wrong error. A tokenization failure should return an error code or an `expected`-style result, not an empty vector.