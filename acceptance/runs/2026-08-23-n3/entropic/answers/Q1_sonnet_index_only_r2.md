## The two calls

`LlamaCppTokenizer::tokenize` (`src/inference/llama_cpp_tokenizer.cpp:49-71`) calls `llama_tokenize` twice unconditionally, every time it runs — not just after a failure:

```cpp
int n = llama_tokenize(vocab_, text.c_str(), text.size(), nullptr, 0, add_special, true);
if (n < 0) { n = -n; }
std::vector<int32_t> tokens(static_cast<size_t>(n));
int actual = llama_tokenize(vocab_, text.c_str(), text.size(), tokens.data(), n, add_special, true);
```

This is `llama_tokenize`'s own documented sizing convention: called with a null output buffer and capacity 0, it returns the *negated* required token count instead of writing anything. The first call is a size probe, the second does the actual write into a correctly-sized buffer. This is the standard two-pass "ask for the size, then fill" idiom C APIs use when they can't allocate on the caller's behalf — I'd call it a **sizing pattern, not retry logic**. Retry implies attempting the same operation again after a failure, possibly with backoff or altered inputs, in hopes of a different outcome. Here the second call is unconditional and always happens, using the size the first call reported; there is no failure branch between the two calls, and the second call never repeats the first — it does something the first one structurally couldn't (write into memory that didn't exist yet).

The other tokenize-adjacent function in the file, `detokenize`, wasn't inspected here, but the same two-call shape is a known llama.cpp convention for `llama_token_to_piece` as well, so I'd expect (not confirmed via the index) a matching pattern there — flagging this as something read from source, not verified structurally.

## Failure value and what callers do with it

`LlamaCppTokenizer::tokenize` fails closed in two places: if `vocab_` is null, or if the second `llama_tokenize` call returns negative `actual`. Both paths `return {}` — an **empty vector**, logged with `logger->error` only in the second case (the null-vocab case fails silently).

That empty vector propagates outward with no signal beyond its own emptiness:

- **`LlamaCppBackend::tokenize`** returns `{}` if `tokenizer_` isn't wired at all, or forwards whatever `tokenizer_->tokenize` returned — so tokenizer failure and "no tokenizer configured" are indistinguishable to every caller above this point.
- **`tokenize_text`** just forwards the (possibly empty) vector — no check.
- **`do_count_tokens`** returns `tokens.size()` — on failure this is **`0`**, identical to what a legitimately empty input string would produce. A caller counting tokens for an empty string and a caller counting tokens for a tokenizer failure get the same answer.
- **`compute_prefix_token_count`** returns `sys_tokens.size()` the same way — `0` on failure, indistinguishable from "no system prefix to tokenize."
- **`do_complete`** doesn't check the token count at all. It calls `tokenize(prompt, false)`, logs `tokens.size()` (which would just print `0`), and passes the vector straight into `decode_loop(tokens, ...)`.
- Inside `decode_loop` → `run_prefill(tokens)`: with `n_tokens == 0`, the batching loop body never executes, so `run_prefill` returns `true` — a **trivial success**, not a failure. `decode_loop` then proceeds into `generate_after_prefill` as if a real (empty) prompt had been prefilled cleanly.

So the failure mode compounds outward as a **type collapse, not a propagated error**: `LlamaCppTokenizer::tokenize`'s explicit failure (bad vocab pointer, negative `llama_tokenize` result) is turned into "zero tokens," which every downstream consumer — count, prefix-length, and full completion — treats as legitimate empty input rather than an error condition. `do_complete` in particular will silently attempt generation against an empty/un-prefilled context rather than surfacing `ENTROPIC_ERROR_GENERATE_FAILED` the way `decode_loop` does for its own two explicit failure branches (missing sampler, prefill decode failure). The index shows no code path that distinguishes "tokenizer genuinely failed" from "caller passed an empty string" anywhere in this chain — that's a real gap, not one I can attribute to a check I simply didn't look at.
