**Short answer:** neither place is retry logic. Both are the standard llama.cpp "ask for the size, then fill the buffer" pattern. The failure path does not retry at all, and the caller gets an empty result that it can't tell apart from a legitimate empty input.

## Why it calls twice

There are two sites, and they follow the same pattern.

**Tokenize** (`src/inference/llama_cpp_tokenizer.cpp:55-63`): The first `llama_tokenize` call passes a null buffer and a size of 0. llama.cpp answers with a negative number whose magnitude is the required token count. The code negates it (line 58), allocates a vector of that size, and calls again to fill it. The second call's return value is the real token count, and the vector is resized to match (line 69).

**Detokenize** (`llama_cpp_tokenizer.cpp:93-104`): Same idea with a 256-byte stack buffer. If the piece doesn't fit, the function returns the negated required size, and the code retries once with an exact-size heap buffer.

The second call is not a retry of a failed call. It is the call that does the work, made with the size the first call reported. Calling it again with identical arguments would not change the outcome, so calling it "retry logic" would be inaccurate.

## What the caller receives on failure

When the second `llama_tokenize` returns a negative value (line 64), `LlamaCppTokenizer::tokenize` logs an error containing only the text length and returns `{}`, an empty vector. The llama.cpp return code is discarded and the text itself is not logged.

Empty is also returned when `vocab_` is null, and `LlamaCppBackend::tokenize` returns empty when `tokenizer_` is unset. So "no vocab", "no tokenizer", "llama failed", and "empty input" all look the same to callers.

## What the callers do with it

| Caller | Behaviour on empty | Notes |
|---|---|---|
| `do_count_tokens` (`llama_cpp_backend.cpp:825`) → `entropic_inference_count_tokens` (`inference_c_api.cpp:548`) | Returns `0` | The C header says "text_len/4 estimate on error", but no exception is thrown on this path, so the `catch(...)` fallback never runs. The `Tokenizer::count_tokens` doc says 0 means empty input, so the API cannot distinguish failure from empty text. |
| `tokenize_text` (`:837`) | Passes empty through | No check. |
| Speculative path (`~:3593`) and MTP path (`~:3921`) | Checks `tokens.size() < 2` and returns `ENTROPIC_ERROR_GENERATE_FAILED` with "must have at least 2 tokens" | The real cause (tokenization failure) is reported as a prompt-length problem. |
| Plain generate, cancellable generate, and stream (`~:2561`, `:2643`, `:2728`) | No check | Empty tokens go into `run_prefill`. With zero tokens the loop body never runs and the function returns `true` (`:1500-1503`). Generation then proceeds with nothing prefilled. I did not trace what sampling does with no logits; it is likely to produce garbage or an llama.cpp error, but I haven't verified that. |
| `complete` (`:3942-3947`) | No check | Same as above. `tokenize(prompt, false)` is passed straight into `decode_loop` (`:3952`). |
| Prefix/system-prompt count (`:2066`) and batch path (`:1911`) | Returns 0 / empty | I did not trace how these feed the prompt-cache and batching logic, so I can't say what they do on failure. |

## Assessment

- The double call is the documented llama.cpp sizing protocol and is correct as written.
- The failure contract is weak. Errors are collapsed into an empty vector, the llama return code is dropped, and most generation paths don't check for empty input. Only the speculative and MTP paths guard against it, and they misreport the cause.
- The C API's documented "estimate on error" behaviour does not match the code.

Possible fixes, if you want them: have the tokenizer return a status alongside the vector (or throw and catch at the seam), log the llama return code and the first bytes of the input, reject empty token sequences in the plain generate, stream and complete paths, and either fix the header comment or implement the estimate fallback for the count path. I have not changed anything in the repo.