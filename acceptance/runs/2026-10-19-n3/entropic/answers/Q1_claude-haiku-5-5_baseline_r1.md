**Why it calls twice:** Both calls are in `LlamaCppTokenizer::tokenize` (`src/inference/llama_cpp_tokenizer.cpp:55` and `:61`). llama.cpp's `llama_tokenize` won't allocate; the caller supplies the buffer. The first call passes `nullptr, 0` to learn the required token count, which comes back as a negative number. The code negates it, sizes the vector, and makes the real call. The second call's `actual < 0` branch is the only real error check, and it is unlikely to fire because the buffer was just sized from the same input.

`detokenize` (`:86-105`) does the same thing with `llama_token_to_piece`. It tries a 256-byte stack buffer first and, if the return is negative, retries with the size llama.cpp reported. That is the second "two calls in a different place."

**Is it retry logic?** No. It is a size query followed by the actual call, and the second call is not retrying a failure. Only the detokenize path reacts to a negative return, and it does so by resizing. Nothing in the code re-attempts a failed tokenization with different parameters.

**What the caller receives on failure:** an empty `std::vector<int32_t>`. In `LlamaCppTokenizer::tokenize` it logs an error with only the input length (`:65`) and returns `{}`. The backend wrapper (`llama_cpp_backend.cpp:788`) passes that through, and it also returns `{}` when no tokenizer is wired, with no log. There is no error channel, so the failure is indistinguishable from an empty prompt.

What the callers do with the empty vector:

| Caller (`llama_cpp_backend.cpp`) | Behavior on empty result | Guard? |
|---|---|---|
| `do_count_tokens` (`:826`) | Returns 0 | None |
| `tokenize_text` (`:839`) | Returns empty vector | None |
| System-prefix count (`:2066`) | Returns 0 | None |
| `do_generate_batch` (`:1911`) | Stores empty per-request token list | Not traced |
| `generate` / `generate_cancellable` / `stream` (`:2561`, `:2643`, `:2728`) | Logs "0 input tokens", continues into `run_prefill_cached` | **None** |
| `complete` (`:3947`) | Continues into `decode_loop` | **None** |
| Speculative (`:3593`) | Returns `ENTROPIC_ERROR_GENERATE_FAILED` if `< 2` tokens | Yes |
| MTP (`:3921`) | Same `< 2` check, returns error | Yes |

The generate, stream, and complete paths have no empty check. From reading `run_prefill` (`:1484`), an empty token vector makes the decode loop run zero times, so it returns `true` without calling `llama_decode`. `decode_loop` then goes on to sampling. I did not run this, so the exact output is unverified. The likely result is sampling from stale or absent logits, or an opaque downstream error, instead of a clean error to the user. The speculative and MTP paths show the codebase already knows the guard is needed, so the three main generation entry points look like an oversight.

**Gaps I did not verify:** whether `do_generate_batch` handles an empty entry in `batch_shared_prefix_len`, and how the public C API surfaces these results. The failure log also omits the input text, which conflicts with the global rule against truncated or partial log context.

**Suggested next step:** add a RED test that feeds an injected tokenizer returning `{}` into `generate`, verify it fails, then add an early `ENTROPIC_ERROR_GENERATE_FAILED` return like the one in the speculative path.