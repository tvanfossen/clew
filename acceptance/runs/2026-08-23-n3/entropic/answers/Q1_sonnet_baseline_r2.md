## The two-call pattern

Both `tokenize` and `detokenize` in `src/inference/llama_cpp_tokenizer.cpp` call the same llama.cpp function twice, but for two different reasons — one is a **size probe**, the other is a **failure-driven retry**.

**`tokenize()` (lines 55–68):** the first call passes `nullptr, 0` as the output buffer — this is llama.cpp's documented convention for "tell me how many tokens this needs." It returns a negative number whose magnitude is the required token count. The code negates it, allocates a vector of exactly that size, and calls `llama_tokenize` again to actually fill it. This is a **size query, not a retry** — the first call is never expected to succeed at writing tokens; it's designed to fail in a specific, informative way every single time. There's no loop, no backoff, and no repetition of the *same* call — it's a fixed two-step probe/fill protocol.

**`detokenize()` (lines 93–104):** this one is more genuinely a retry. It optimistically calls `llama_token_to_piece` against a 256-byte stack buffer, hoping that's big enough (it almost always is — most token pieces are a few bytes). Only if that returns negative (buffer too small) does it fall back to a second call sized exactly to `-n`. This *is* fair to call retry logic — it's optimistic-buffer-then-retry-on-failure — but it's a single, bounded, one-shot retry against a different-sized resource, not a retry against a transient/recoverable error. There's no backoff, no retry limit counter, and no possibility of a third attempt: if the second call also fails, the code gives up immediately.

So: `tokenize`'s two calls are a mandatory two-phase protocol (never skippable), while `detokenize`'s two calls are a fast-path/fallback pair (skippable when the stack buffer is big enough). Only the latter deserves the word "retry," and even then it's a narrow, single-attempt variant — not resilience/retry-loop logic in the sense of retrying against unreliable I/O.

## Following the failure outward

**On failure, both functions return an empty value with no error signal in the type itself:**
- `tokenize()` returns `{}` (empty `std::vector<int32_t>`) when `vocab_` is null, or when the second `llama_tokenize` call returns a negative `actual` count (logged as an error at `llama_cpp_tokenizer.cpp:65-67`).
- `detokenize()` returns `{}` (empty `std::string`) when `vocab_` is null, or when the retried call returns `n <= 0`.

**`LlamaCppBackend::tokenize`/`detokenize`** (`llama_cpp_backend.cpp:788-816`) pass this straight through — no check for the failure case, just a copy/forward. The doc comments even say explicitly "Returns empty when no tokenizer is wired — matches prior failure-path return," conflating "no tokenizer" with "tokenizer failed" into the same empty-vector signal.

**Every caller downstream treats an empty token vector as if it were a legitimate empty prompt, not a failure:**
- `do_generate_text_only` (`llama_cpp_backend.cpp:2561`, `2643`) calls `tokenize(prompt, true)`, logs `tokens.size()` (which would just read `0`), and passes it straight to `run_prefill_cached`.
- `run_prefill` (`llama_cpp_backend.cpp:1484-1503`) loops `for (int i = 0; i < n_tokens; ...)` — with `n_tokens == 0` this loop body never executes, `llama_decode` is never called, and the function returns `true` (success).
- So a tokenization failure doesn't propagate an error at all — it silently becomes a "successful" prefill of zero tokens, and generation proceeds against an effectively unprimed/empty context, indistinguishable from a caller who genuinely passed an empty string.

This is worth flagging as a real gap: **there is no way for a caller to distinguish "tokenizer failed" from "input was empty."** The only trace of the failure is a log line at ERROR level inside `llama_cpp_tokenizer.cpp:65-67` — nothing sets `GenerationResult::error_code`, nothing short-circuits `do_generate_text_only`, and the eventual `GenerationResult` will report a normal `finish_reason` (`"stop"` or hitting `max_tokens`) built from a model that was never actually given the prompt. A user would see a nonsensical/generic completion with no indication tokenization ever failed, and would have to go digging in logs to find out why.

One place this is at least partially covered: `detokenize` failures during streaming generation (`llama_cpp_backend.cpp:1534`, `1819`) just append an empty string to `generated`/`r.content` — a dropped token silently disappears from the output rather than corrupting or erroring, which is the more benign version of the same "empty means nothing happened" pattern.
