**Short answer:** the two `llama_tokenize` calls are a size-query followed by a fill, not retry logic. Tokenization failure is reported as an empty vector, and the callers don't check for it.

## Why it calls twice

Both calls are in `LlamaCppTokenizer::tokenize` (`src/inference/llama_cpp_tokenizer.cpp:49-71`), at lines 55 and 61, not in two separate places. The first call passes a null buffer with size 0. llama.cpp then returns the negative of the token count it needs. The code flips the sign to get `n`, allocates a vector of that size, and calls again to fill it. The second call is unconditional and never depends on the first failing.

Calling it "retry" is misleading. The header comment at line 44-45 calls the second call the "sized retry", and I'd rename it to "sizing call" to match what it does. The only real retry-style code is in `detokenize` (lines 92-104), which resizes a buffer after a too-small result.

One edge to check: `-n` on the sizing result is undefined behaviour if llama.cpp returns `INT32_MIN` for an oversized input. I haven't verified what the pinned llama.cpp returns in that case.

## What the caller receives on failure

Failure is signalled only by an empty `std::vector<int32_t>`:

| Layer | Behaviour on failure | Location |
|---|---|---|
| `LlamaCppTokenizer::tokenize` | Logs an error, returns `{}` | `llama_cpp_tokenizer.cpp:64-67` |
| `LlamaCppBackend::tokenize` | Returns `{}`; also returns `{}` silently when no tokenizer is wired | `llama_cpp_backend.cpp:788-800` |

Empty is also a valid result for empty input with `add_special=false`, so a caller cannot tell "failed" from "nothing to encode."

## What the callers do with it

- **Plain generation and streaming** (`llama_cpp_backend.cpp` around 2561, 2643, 2728): these call `tokenize(prompt, true)`, log "0 input tokens", and continue to `run_prefill_cached`. Nothing checks `tokens.empty()`. `run_prefill` with zero tokens runs no `llama_decode`, returns true, and sampling proceeds. What the sampler then produces depends on whatever logits are left in the context. I did not trace that path to confirm, so treat it as a likely silent-garbage path rather than a verified one.
- **Raw completion** (`do_complete`, around 3947): same pattern. `decode_loop` is entered with an empty prompt.
- **Speculative and MTP** (around 3593, 3921): the only callers that treat an empty result as an error. They check `tokens.size() < 2` and return `ENTROPIC_ERROR_GENERATE_FAILED`. That check also rejects legitimate one-token prompts, and the error message blames the prompt length, not the tokenizer.
- **Batch** (around 1911): empty sequences reach `batch_shared_prefix_len`, which returns 0 for an empty sequence. Whether the batch path then fails cleanly is unverified.
- **Prefix sizing** (`compute_prefix_token_count`, around 2051): returns 0 on tokenizer failure, which passes a zero-length prefix into `prefill_and_cache_prefix`. What that does is unverified.
- **Token counting** (`do_count_tokens` → C API `entropic_inference_count_tokens`): returns 0. Callers cannot distinguish this from an empty string. The C API's `catch` path returns `len/4` instead, so an exception and a tokenizer failure give different answers.

The unit tests mock the `Tokenizer` seam, and the real adapter is excluded from the CPU-only gate by design. Nothing in the unit suite exercises the empty-on-failure path against the real adapter.

## Recommendation

The core problem is the contract. Failure should not look like an empty result. Options:

1. Change `Tokenizer::tokenize` to return a status (e.g. `std::optional` or an error out-param), then have the generate paths fail with `ENTROPIC_ERROR_GENERATE_FAILED`, matching the speculative path.
2. Keep the signature and add a `tokenize_ok()` check at the generate entry points.

Option 1 changes `include/entropic/inference/tokenizer.h`, a public header. Per your `.claude/CLAUDE.md`, interface changes are design changes that need your approval, so I have not made it. Tell me which option you want and I'll write the proposal and the failing test first.