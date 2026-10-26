**Why it calls twice:** It's a size-then-fill query, not retry. In `LlamaCppTokenizer::tokenize` (`src/inference/llama_cpp_tokenizer.cpp:49-71`), the first `llama_tokenize` call passes a null buffer and length 0. llama.cpp answers with the negative of the required token count, which the code negates. The code then allocates that many slots and makes the second call to fill them. Each call is a single attempt, with no loop, backoff, or re-try on failure. The doc comment on the method calls the second call a "sized retry," which is misleading. I found only this one pair of `llama_tokenize` calls. If you meant a different pair, such as `mtmd_tokenize` in `mtmd_prefill`, the index didn't surface it and I didn't verify it.

**What the caller receives on failure:** The tokenizer returns an empty vector. It logs `Tokenization failed for text of length N` only when the second call returns negative. A null `vocab_` returns empty silently. `LlamaCppBackend::tokenize` (`llama_cpp_backend.cpp:788-800`) passes that through, and it also returns empty when no tokenizer is wired. There is no error code and no exception, so an empty result can't be told apart from a legitimately empty token sequence.

**What the callers do with it:**

| Caller | Result on empty | Consequence |
|---|---|---|
| `tokenize_text` (public API) | empty vector | Documented as "empty if COLD or error," so the caller can't tell which |
| `do_count_tokens` / `count_tokens` | `0` | A plausible-looking count. A caller budgeting context would conclude the prompt fits. |
| `do_complete` (`llama_cpp_backend.cpp:3941`) | proceeds with 0 input tokens | Logs "0 input tokens" and calls `decode_loop` anyway |
| `decode_loop` → `run_prefill` | returns `true` | `run_prefill` with zero tokens skips the decode loop and returns success. `decode_loop` only checks sampler creation and prefill, so generation runs with nothing prefilled. |
| `compute_prefix_token_count` → `prefill_dispatch` | `0` | `prefill_and_cache_prefix` treats 0 as "no prefix" and falls back to plain prefill without caching |

The main risk is `do_complete`. A tokenization failure is logged once inside the tokenizer and then turns into a successful generation over no prompt. I didn't read `generate_after_prefill`, so what it does with zero prefilled positions is inferred, not verified. The `decode_loop` error branches only cover sampler and prefill failures, which is consistent with that reading.