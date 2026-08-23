## The two-call site

Both calls happen in one place: `entropic::LlamaCppTokenizer::tokenize` (`src/inference/llama_cpp_tokenizer.cpp:49-71`):

```cpp
int n = llama_tokenize(vocab_, text.c_str(), text.size(), nullptr, 0, add_special, true);
if (n < 0) { n = -n; }

std::vector<int32_t> tokens(n);
int actual = llama_tokenize(vocab_, text.c_str(), text.size(), tokens.data(), n, add_special, true);
```

This is llama.cpp's documented two-phase sizing convention, not entropic's own invention: `llama_tokenize` is called first with a null buffer/`n_max_tokens=0` purely to get the required token count back as a negative size, then called again with a buffer of exactly that size to actually fill it. It's the same "ask the size, then fill it" pattern as `snprintf(nullptr, 0, ...)`.

**This is not retry logic.** Retry implies the same operation is repeated because it might fail/succeed differently on a later attempt (transient failure, contention, backoff). Here the two calls have two different purposes and neither is a repetition of the other — call 1 always returns a *negative* size(a query), call 2 does the actual write. There's no failure/success branching between them, no backoff, and the second call is unconditional on the first. It's a sizing probe followed by the real call, which is a standard C-API idiom, not resilience logic.

## Following the failure outward

The only place inside `tokenize` that can produce a genuine failure is `actual < 0` from the second call — that's when `llama_tokenize` itself reports an error on the real fill. In that branch:

```cpp
if (actual < 0) {
    logger->error("Tokenization failed for text of length {}", text.size());
    return {};
}
```

It logs and returns an **empty `std::vector<int32_t>`**. `vocab_ == nullptr` also returns `{}` earlier, with no log at all.

That empty vector is indistinguishable, at the type level, from "the input text legitimately tokenized to zero tokens" (e.g., an empty string). Nothing downstream carries an error flag — it's just `{}` either way.

Tracing callers of `LlamaCppBackend::tokenize` (which just forwards to the seam):

- **`do_count_tokens`** — `tokens.size()` → returns `0`. A tokenizer failure is reported to the API caller as "this text has zero tokens," identical to counting an empty string.
- **`tokenize_text`** — returns the empty vector straight through to whatever public API called it. No error surfaces.
- **`compute_prefix_token_count`** — `sys_tokens.size()` → returns `0`, same value as the legitimate "no system messages present" early-return a few lines earlier. A tokenizer failure and "there was nothing to tokenize" collapse to the same signal.
- **`do_complete`** — this is the one that matters most. It does **no check at all** on the result of `tokenize(prompt, false)`; it logs `tokens.size()` (which will just print `0`) and passes the empty vector straight into `decode_loop(tokens, ...)`. Inside `decode_loop`, that reaches `run_prefill(tokens)`, whose loop is `for (int i = 0; i < n_tokens; ...)` — with `n_tokens == 0` the loop body never executes, `llama_decode` is never called, and the function falls through to `return true;`. So a tokenizer failure on the completion path doesn't produce `ENTROPIC_ERROR_GENERATE_FAILED`; prefill reports success on an empty context, and the request proceeds into sampling/generation as if given an empty prompt, rather than surfacing the tokenizer error.

So the failure mode here is: a genuine `llama_tokenize` error is logged once at the point of origin, then silently reshaped into "empty input" all the way up the stack, and on the generation path it's absorbed into a synthetic prefill success rather than reaching the caller as an error at all. The index can't tell me whether this is an accepted, deliberate trade-off (comment says "matches the prior failure-path return shape," implying it's intentional continuity with older behavior) or an unnoticed gap — that's a judgment call for whoever owns `LlamaCppBackend`, not something the graph settles.
