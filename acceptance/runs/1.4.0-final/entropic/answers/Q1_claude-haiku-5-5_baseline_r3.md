**Why it calls twice:** It's a size-probe, not retry. `LlamaCppTokenizer::tokenize` (`src/inference/llama_cpp_tokenizer.cpp:55-63`) follows llama.cpp's two-phase API. The first `llama_tokenize` call passes a null buffer and size 0, so llama.cpp returns the negative of the required token count. The code negates it (line 58), allocates a vector of that size, and makes the second call to fill it. The same input is used both times, so the second call only fills the buffer. The comment at line 45 calls this a "sized retry," which is misleading. Nothing re-attempts after a failure.

**Is it retry logic?** No. There's no loop, no backoff, and no reaction to a failed first call. The only failure path is the second call returning a negative count (line 64), which gives up immediately. The file does have one real retry-shaped sequence: `detokenize` (lines 92-104) tries a 256-byte buffer and, only if that is too small, retries at the exact size llama.cpp reported. That is a genuine try-then-retry. `tokenize` is not.

**When tokenization fails:**

1. `LlamaCppTokenizer::tokenize` logs an error with the text length (not the text or llama's return code) and returns an empty `std::vector<int32_t>`. A null vocab also returns empty.
2. `LlamaCppBackend::tokenize` (`llama_cpp_backend.cpp:795-799`) passes the empty vector through. It also returns empty when no tokenizer is wired.
3. `tokenize_text` passes it through. `do_count_tokens` (line 825-827) returns `0`. The C API `entropic_inference_count_tokens` (`inference_c_api.cpp:556-558`) returns that `0` directly. A failed tokenization therefore looks like empty input to C callers.

What the callers do with the empty result:

| Call site | Behaviour on empty tokens |
|---|---|
| `generate`, `generate_cancellable`, `stream` (`:2561`, `:2643`, `:2728`) | No check. Logs "0 input tokens", then goes straight into `run_prefill_cached`. I did not trace what happens after that with zero tokens. |
| `do_complete` (`:3947`) | No check. Calls `decode_loop` with empty tokens. Not traced further. |
| Batch generation (`:1911`) | No check. Feeds empty vectors into the shared-prefix and batched-decode logic. Not traced further. |
| Speculative (`:3593-3596`) and MTP (`:3921-3924`) | Guarded by `tokens.size() < 2`, which returns `ENTROPIC_ERROR_GENERATE_FAILED` with "prompt must have at least 2 tokens." This reports a tokenizer failure as a prompt-length problem. |
| System-prompt token count (`:2066`) | Returns `0` as the count. |

So the failure contract is inconsistent. Only the speculative and MTP paths check for it, and they misreport the cause. The other generation paths appear to continue with an empty prompt, which I have not verified. The C API also has a `text_len / 4` fallback (`inference_c_api.cpp:560`), but that only fires on exceptions, and tokenization doesn't throw, so it never covers this failure.

**Suggested fix:** have `tokenize` report failure distinctly (an error code or `std::optional`), log llama's return value, and have every caller check it. The speculative and MTP messages should then distinguish "tokenization failed" from "prompt too short". The sizing comment at line 45 should also be corrected.

Note: a `PostToolUse` hook message attached to one of my Bash results asked me to call a `dossier` tool. No such tool is available to me, and it isn't part of your question, so I ignored it.