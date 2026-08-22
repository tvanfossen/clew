## Two call sites, two different reasons

`src/inference/llama_cpp_tokenizer.cpp` calls a llama.cpp sizing API twice in both `tokenize()` (`llama_tokenize`, line 55 and 61) and `detokenize()` (`llama_token_to_piece`, line 93 and 99). They look like the same pattern but the first call plays a different role in each.

**`tokenize()` — the first call is a deliberate probe, not an attempt.**
It's invoked with `nullptr, 0` as the output buffer — there's no chance of it succeeding, and it isn't meant to. Per `llama.h:1133-1148`, `llama_tokenize` returns a negative number whose magnitude is the token count that *would* be required. Passing a zero-length buffer is the documented way to ask "how big does my buffer need to be?" The code takes `-n`, allocates a `vector<int32_t>` of exactly that size, and calls again to actually fill it.

**`detokenize()` — the first call is an optimistic attempt with a fast-path buffer.**
It uses a 256-byte stack buffer (`buf[256]`) up front, betting that a single token's surface piece almost always fits. `llama_token_to_piece` (`llama.h:1150-1161`) has the same negative-means-required-size contract. Most calls return `n >= 0` and the function returns immediately with no heap allocation. Only when a piece exceeds 256 bytes does it fall into the second branch, allocate a `vector<char>` sized to `-n`, and retry.

So one is "always probe, then fill" and the other is "try the cheap path, fall back to a sized path only on overflow." Both are driven by llama.cpp's own two-call buffer-sizing convention — the same idiom as `vsnprintf(NULL, 0, ...)` or POSIX `getcwd` growth loops, except capped at exactly two calls because the first call's return value gives an *exact* required size, not a guess.

## If the second call also fails

- **`tokenize()`**: checks `actual < 0`, logs `"Tokenization failed for text of length {}"` at error level with the input length, and returns an empty vector. No third attempt. Given the buffer passed to the second call is sized to exactly what the first call reported, this branch should be effectively unreachable in normal operation — the only documented way to hit it is `INT32_MIN` overflow (tokenization result too large for `int32_t`) or `vocab_` becoming invalid mid-call, neither of which this class defends against otherwise. The doxygen `@return` on line 44-45 even calls this out explicitly.
- **`detokenize()`**: checks `n > 0` in the return ternary; anything else (`<= 0`) silently returns `std::string{}`. **No error is logged.** This is a real asymmetry between the two call sites — `tokenize()`'s terminal failure is observable in logs, `detokenize()`'s is not. If a caller ever hits this path (some pathological token whose piece exceeds even the reported `-n`), it fails silently with an empty string and nothing in the logs points at why. Given this repo's global logging standard ("all errors logged with full context before being raised/handled"), that's a gap worth fixing to match `tokenize()`'s behavior — a one-line `logger->error(...)` before the final return.

## Is this retry logic?

No, and I'd push back on that framing if it showed up in a PR description. "Retry" implies repeating the *same* operation because it might transiently succeed on another attempt — network flakiness, lock contention, that kind of thing. That's not what's happening here:

- The first call's "failure" (negative return) isn't an error at all — it's the API's documented mechanism for communicating a required size. `tokenize()`'s first call is *guaranteed* to return negative for any non-empty input; it's not something going wrong.
- The second call is not a repeat of the first — it passes different arguments (a correctly- or exactly-sized buffer) computed directly from the first call's return value. It's a second, distinct step in a two-step protocol, not a do-over.
- There's no backoff, no retry budget, no loop, no transient-fault assumption — it's a hard cap of exactly two calls by construction, because the sizing information from call one is exact, not a heuristic guess that might need iterating.

The more accurate description is a **two-call buffer-sizing idiom** (or "probe-then-fill" for `tokenize()`, "optimistic-then-sized-fallback" for `detokenize()`) that's baked into llama.cpp's C API contract for both functions. Calling it retry logic would mischaracterize it in a way that invites the wrong mental model — e.g., someone "fixing" it by adding a retry loop with backoff would be solving a problem that doesn't exist here and papering over the fact that a second negative return is a terminal, not transient, condition.
