This confirms the picture. Here's what's going on.

## Why the tokenizer calls llama.cpp twice

`LlamaCppTokenizer::tokenize` (`src/inference/llama_cpp_tokenizer.cpp:49-71`) calls `llama_tokenize` twice back to back:

1. First call passes `nullptr, 0` for the output buffer. `llama_tokenize`'s documented contract is: if the buffer is too small (or absent), it returns the *negative* required token count instead of writing anything.
2. The code negates that (`n = -n`), allocates a `std::vector<int32_t>` of exactly that size, and calls `llama_tokenize` again with the real buffer to actually fill it.

`detokenize` (line 86-105) does the analogous thing for `llama_token_to_piece`, but conditionally: it tries a fixed 256-byte stack buffer first (cheap, no allocation, sufficient for the overwhelming majority of pieces), and only falls back to a second call with a heap buffer sized from the negative return if the piece didn't fit.

**This is not retry logic.** Retry logic re-attempts an operation that may have *failed* transiently, on the assumption a second attempt might succeed. Here the second call isn't compensating for a failure — the first call is a deliberate, expected *measurement* probe (llama.cpp's sizing-callback convention, the same pattern as `snprintf(NULL, 0, ...)`). Both calls succeed by design every time; the second call's job is to fill a correctly-sized buffer discovered by the first, not to recover from an error the first one hit. Nothing loops, nothing backs off, nothing distinguishes "worked" from "didn't work" between the two calls — it's a fixed two-step protocol dictated by the callee's API shape, not error handling.

## Following an actual failure outward

`llama_tokenize` can still return negative on the *second* call (line 64) — that's the real failure case, distinct from the sizing convention. When that happens:

- `LlamaCppTokenizer::tokenize` logs an error and returns `{}` (empty vector) — line 66-67.
- `LlamaCppBackend::tokenize` (`llama_cpp_backend.cpp:788-800`) does no failure check at all; it just copies whatever it got, so an empty vector passes straight through.
- Every downstream caller — `do_count_tokens`, `tokenize_text`, `do_generate_text_only`, `do_generate_batch`, `do_complete` — calls `tokenize()` and uses the result directly. **None of them check `tokens.empty()`** (confirmed by grep: zero hits for that check across the whole file).

The empty vector is indistinguishable from "the caller passed an empty string," and it's silently treated as valid input rather than an error:

- `do_count_tokens` reports `0` tokens — same as an empty prompt.
- `run_prefill(tokens)` (line 1484-1503) loops `for (int i = 0; i < n_tokens; i += n_batch)`; with `n_tokens == 0` the loop body never executes and the function returns `true` — a *successful* prefill of nothing.
- `decode_loop`/`run_prefill_cached` therefore proceed straight into generation with an empty KV cache and no error, so the model generates unconditioned on any prompt — a silent quality failure, not a surfaced one.
- `do_generate_batch` folds the empty vector into `batch_shared_prefix_len`/`total_suffix` arithmetic with no special case.

The one place this coincidentally gets caught is `generate_mtp` (line 3906-3931), which checks `tokens.size() < 2` and returns `ENTROPIC_ERROR_GENERATE_FAILED` — but that guard exists because MTP's speculative-decoding kernel needs at least 2 tokens, not because anyone anticipated a tokenizer failure. It happens to convert the failure into a real error only in that one code path; everywhere else (`do_complete`, `do_generate_text_only`, `do_generate_batch`) a hard tokenizer failure degrades silently into "generate from nothing" rather than surfacing to the API caller as an error.
