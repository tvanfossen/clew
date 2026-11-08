**Short answer:** the two llama.cpp calls are a size-probe and a fill, not retry. A failed tokenization returns an empty vector, and the callers mostly don't check for it. The failure is silent in most paths.

**Why it calls twice (`src/inference/llama_cpp_tokenizer.cpp:49-71`)**

`LlamaCppTokenizer::tokenize` calls `llama_tokenize` at lines 55 and 61:

1. First call passes a null buffer and size 0. The code's comment says a negative return is the required token count, so the call is asking llama.cpp how big the output must be. The code negates it (`n = -n`).
2. It allocates a vector of that size and calls `llama_tokenize` again with the buffer.

The second call is the only real work. The `actual < 0` check after it is defensive, since the size was just measured on the same input.

The other two-call site is `LlamaCppTokenizer::detokenize` (`llama_cpp_tokenizer.cpp:86-105`, `llama_token_to_piece` at lines 93 and 99). It tries a fixed 256-byte stack buffer first. If llama.cpp returns a negative size, it allocates exactly that and calls again. That is a buffer resize, not a retry.

**Is it retry logic?** No. Neither site repeats on failure: there is no loop, no backoff, and no second attempt on the same input. The only "failure" branch is the second call returning negative, which logs an error and returns `{}`.

**What the caller receives on failure**

- `LlamaCppTokenizer::tokenize` returns an empty vector. It also returns empty when `vocab_` is null, and it logs only in the negative-return case (`"Tokenization failed for text of length N"`).
- `detokenize` returns an empty string on failure.
- `LlamaCppBackend::tokenize` (`llama_cpp_backend.cpp:788-800`) passes the empty result through. It returns empty when no tokenizer is wired, with no log.

Downstream, the empty vector propagates without a check:

| Caller | What it does with empty tokens |
|---|---|
| `tokenize_text` (`llama_cpp_backend.cpp:837`) | Returns empty. |
| `do_count_tokens` (`:825`) | Returns `0`. |
| `InferenceBackend::count_tokens` (`backend.cpp:496`) | When loaded, returns `0` directly. The `len/4` estimate applies only when COLD. |
| `entropic_inference_count_tokens` (`inference_c_api.cpp:548`) | Returns `0`. The `len/4` fallback runs only on an exception. |
| `compute_prefix_token_count` (`:2051`) | Returns `0`, so prefill caches a zero-length prefix. |
| `do_complete` (`:3941`) and `do_generate_text_only` (`:2555`) | Log "0 input tokens" and continue into `decode_loop` / `run_prefill_cached`. |

`run_prefill` (`:1484`) does not fail on an empty token list: its loop simply doesn't execute and it returns `true`. Nothing in the generation path surfaces the tokenization failure as an error result.

**Observations**

- A loaded model whose tokenization fails reports `0` tokens from `count_tokens`. A COLD model reports a `len/4` estimate for the same text. That is an inconsistency, and a caller budgeting context will see a silent undercount.
- The generation path for an empty prompt is the least certain part of this. The index shows that `run_prefill` returns `true` for zero tokens. I did not verify what llama.cpp does when `generate_after_prefill` samples without a prefilled context. Check that before relying on the behaviour.
- The index doesn't cover llama.cpp itself. The "negative return = required size" reading comes from the code's own comment and standard llama.cpp usage, not from the library source.