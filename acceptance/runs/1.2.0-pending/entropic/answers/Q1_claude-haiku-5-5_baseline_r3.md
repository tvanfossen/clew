**Short answer:** The two calls are a sizing probe followed by the real call. It is not retry logic. On failure, the caller gets an empty vector with no error code, and most callers don't check for it.

## Why it calls twice

`LlamaCppTokenizer::tokenize` (`src/inference/llama_cpp_tokenizer.cpp:49-71`) makes two `llama_tokenize` calls:

1. **Line 55:** passes a null buffer with capacity 0. llama.cpp returns the negative of the required token count, so `n = -n` gives the size.
2. **Line 61:** allocates `n` slots and calls again to fill them.

This is the usual two-phase C buffer pattern. Nothing is retried. The first call is a measurement, and the second call does the work. A failure on the second call returns `{}` at line 67. The header comment at line 45 calls this a "sized retry", which is a misleading name for it. `detokenize` at lines 93 and 99 uses the same probe-then-fill pattern with `llama_token_to_piece`.

## What the caller receives on failure

`LlamaCppTokenizer::tokenize` returns `{}`. The only signal is one `logger->error` line (line 65). A `vocab_ == nullptr` check also returns `{}` silently. Nothing propagates an error code.

The empty vector passes up unchanged:

- `LlamaCppBackend::tokenize` (`llama_cpp_backend.cpp:788-800`) copies it through.
- `do_count_tokens` (line 825) returns `0`. `count_tokens` and the C API `entropic_inference_count_tokens` return `0` too. A caller doing budget math sees "zero tokens" and thinks the prompt fits.

## What the callers do with it

| Call site | Empty vector leads to |
|---|---|
| `do_generate_text_only` (~2561), cancellable (~2643), streaming (~2728) | Logs "0 input tokens", then calls `run_prefill_cached`. `run_prefill` (1484-1502) loops zero times and returns `true`, so the generation step proceeds with no prompt decoded. No empty check exists at these sites. |
| Speculative (~3593) and MTP (~3921) | Checks `tokens.size() < 2` and returns `GENERATE_FAILED` with "must have at least 2 tokens". The error is real, but the message blames the prompt, not the tokenizer. |
| `do_complete` raw (~3947) | Goes straight to `decode_loop` with no check. |
| Prefix sizing (~2060) | Returns 0, so caching silently falls back to a plain prefill. |
| Batch generate (~1911) | Feeds `batch_shared_prefix_len` and `t.size() - shared`. I did not check that for the empty case, so I can't say whether it misbehaves. |

Two things I did not verify by running code. First, I did not trace what `decode_loop` does with an empty token list, so the claim that generation runs without a prompt is an inference from `run_prefill`. Second, I did not find a unit test that exercises the `llama_tokenize` failure path. The `.cpp` is excluded from the unit gate by design, and the seam tests only cover the null-vocab and mock cases.

## Suggested fix

Make tokenization failure a distinct result instead of an empty vector. Either return `std::optional`/an error code from `Tokenizer::tokenize`, or have `LlamaCppBackend::tokenize` return an error that the generate entry points check before prefill. That would also let `count_tokens` report failure instead of `0`. This changes the `Tokenizer` interface, which the architecture docs treat as a design change, so it needs your sign-off before I touch it.