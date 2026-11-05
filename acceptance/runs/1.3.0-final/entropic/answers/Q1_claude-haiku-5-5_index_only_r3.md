**Short answer:** the two `llama_tokenize` calls are not in two different places, and they are not retry logic. They are one function making a sizing call and then a fill call. When tokenization fails, the caller gets an empty vector, and most callers then continue as if the prompt were empty.

**Why it calls twice**

Both calls are in `entropic::LlamaCppTokenizer::tokenize` (`src/inference/llama_cpp_tokenizer.cpp:49-71`), at lines 55 and 61:

1. First call passes a null buffer and size 0. llama.cpp reports the required token count as a negative number, which the code flips to a positive size.
2. It allocates a vector of that size and calls `llama_tokenize` again to fill it.
3. A negative return on the second call is treated as failure: it logs an error with the text length and returns `{}`. On success it resizes to the actual count.

This is the usual two-pass protocol for sizing a buffer. The second call is not retried on the same input after a failure, and nothing loops. The only other llama.cpp tokenize-related call the index shows is in `LlamaCppBackend`, which delegates to the `Tokenizer` seam rather than calling llama.cpp directly.

I could not find a second, separate `llama_tokenize` site in the index. If you were thinking of a different pair, point me at the symbol and I'll check it.

**What the caller receives on failure**

| Layer | On failure | Notes |
|---|---|---|
| `LlamaCppTokenizer::tokenize` | `{}` | Logs at error level. A null `vocab_` also returns `{}`, silently. |
| `LlamaCppBackend::tokenize` | `{}` | Pass-through. Also returns `{}` when no tokenizer is wired. |
| `do_count_tokens` | `0` | Indistinguishable from empty input. |
| `tokenize_text` | empty `vector` | Public API; callers can't tell failure from an empty string. |
| `compute_prefix_token_count` | `0` | Its only caller is `prefill_dispatch`, which then passes a zero-length prefix into `prefill_and_cache_prefix`. I did not trace that path further. |
| `do_complete` | proceeds with empty tokens | Logs "0 input tokens", then calls `decode_loop`. |

**The problematic path is `do_complete`**

- `decode_loop` calls `run_prefill(tokens)`.
- `run_prefill` with an empty vector runs zero loop iterations and returns `true`. It has already cleared the KV memory with `llama_memory_clear` at line 1485.
- So a tokenization failure in `do_complete` turns into sampling with no prompt decoded, and it returns no error to the caller. The index does not show what `generate_after_prefill` does in that state, so I can't say what text comes out. The failure is not surfaced as an error.

**Implications**

- Tokenization failure is logged at the tokenizer level only. The backend and the public APIs return empty or zero with no error code.
- `count_tokens` returning 0 and `do_complete` silently running on nothing are both wrong if the caller relies on the result.
- A fix would need an error channel from `tokenize` (for example, a status out-parameter or an exception-free error return) and checks in `do_complete`, `do_count_tokens` and `compute_prefix_token_count`. Note that the interface header `include/entropic/inference/tokenizer.h` is documented as immutable without a new proposal, so this is a design change that needs your sign-off.