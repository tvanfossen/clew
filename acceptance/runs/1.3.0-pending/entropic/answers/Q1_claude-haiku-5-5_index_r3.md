**Short answer:** the two llama.cpp calls are a size-query-then-fill idiom, not retry logic. Neither call retries a failed tokenization. The failure reaches callers as an empty vector or empty string, and most callers do not check for it.

## Why it calls twice

llama.cpp's `llama_tokenize` and `llama_token_to_piece` return a negative number when the output buffer is too small, and its magnitude is the size needed. The wrapper uses that to size its buffer.

| Location | First call | Second call | Retry? |
|---|---|---|---|
| `LlamaCppTokenizer::tokenize`, `src/inference/llama_cpp_tokenizer.cpp:55-61` | `nullptr, 0` to get the token count | Fills a vector of that size | No. The first call is a query, not an attempt. |
| `LlamaCppTokenizer::detokenize`, `llama_cpp_tokenizer.cpp:93-101` | 256-byte stack buffer | Only if the first returns negative, re-calls with an exact-size heap buffer | Closest to retry, but it is buffer growth triggered by a size signal, not a failure retry. |

The code's own wording makes this easy to misread. The detokenize comment says "retry with exact size" (`:97`), and the tokenize doc calls the second call "the sized retry" (`:45`). Both are resizing, not retrying. I would reword those comments.

## What the caller receives on failure

Failure in `tokenize` is a `logger->error` (`:64-68`) followed by `return {}`. Only the text length is logged, not the text. The same empty return is used for a null vocab (`:52`), so an invalid vocab is silent. `detokenize` returns `""` on failure with no log at all.

The empty vector is the same value a legitimately empty input produces, so callers cannot tell "no tokens" from "failed."

## What callers do with it

| Caller | What happens on empty | Evidence |
|---|---|---|
| `LlamaCppBackend::tokenize` (`llama_cpp_backend.cpp:796`) | Passes through. Returns `{}` when `tokenizer_` is null. | `:795-799` |
| `do_count_tokens` (`:825-828`) | Returns `0`. | Read directly |
| `entropic_inference_count_tokens` (`inference_c_api.cpp:556-560`) | Returns `0` to the C caller. | Read directly |
| `tokenize_text` (`:837-841`) | Returns an empty vector. Doc says "empty if … error." | `backend.h:273` |
| MTP path (`:3921-3925`) | Checks `tokens.size() < 2` and returns `ENTROPIC_ERROR_GENERATE_FAILED` with "MTP prompt must have at least 2 tokens." This is the only caller that checks, and it reports a tokenize failure as a too-short prompt. | Read directly |
| `do_generate_text_only` (`:2561-2572`) | Logs "0 input tokens", then calls `run_prefill_cached` with an empty sequence. `run_prefill` with zero tokens only clears memory and returns true (`run_prefill` body, `:1484-1503`). So generation likely continues from an empty context with no error. | Read from `run_prefill`; the downstream sampling step is not read |
| `do_complete` (`:3947`) | Same as above: `decode_loop` → `run_prefill` (empty, succeeds) → `generate_after_prefill`. | Dossier call graph |
| Batch path (`:1911-1915`) | Empty sequences go into the shared-prefix and viability math. | Not traced |
| Streaming and batch detokenize (`:1534`, `:1819`) | An empty piece is appended, so the failed token's text silently disappears from the output. | Read directly |

## Problems this exposes

1. **Doc/behavior mismatch in the C API.** The header for `entropic_inference_count_tokens` says it returns "text_len/4 estimate on error." The fallback is in a `catch(...)`, but a tokenize failure does not throw. The caller gets `0` instead.
2. **Failure is indistinguishable from empty input.** Nothing in the chain carries an error code, so the generate paths cannot tell a tokenize failure from a legitimately empty prompt.
3. **Empty prompts proceed into generation.** I have not verified what `generate_after_prefill` does with no prefill. It may fail later with a less useful error, or sample from stale logits.
4. **The `actual < 0` branch is probably unreachable.** Under the documented contract, the second call should not return negative for the same input. I have not checked this against the pinned llama.cpp source.

## Not verified

I did not read `try_warm_reuse`, `prefill_dispatch`, `generate_after_prefill`, the system-prompt tokenize at `:2066`, or the batch helpers. The claims about empty-prompt behavior past `run_prefill` are inferences from the call chain, not from reading those bodies.