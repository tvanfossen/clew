**Short answer:** the two calls are not in two places. Both are in `LlamaCppTokenizer::tokenize` (`src/inference/llama_cpp_tokenizer.cpp:55` and `:61`). It is a size-then-fill pair, not retry logic.

**Why it calls twice**

llama.cpp's `llama_tokenize` needs a buffer sized in advance. The first call passes a null buffer and length 0. It returns the negative of the token count it would need. The code negates that to get `n`, allocates `n` slots, and makes the second call to fill them. The second call's return value is the real token count, and the vector is resized to it.

There is no loop, no backoff, and no second attempt after a failure. The comments at `llama_cpp_tokenizer.h:45` and `llama_cpp_tokenizer.cpp:45` say "sized retry", which is misleading. I'd reword that comment to "two-pass sizing".

The other llama.cpp tokenize call is `mtmd_tokenize` at `llama_cpp_backend.cpp:2407`, on the multimodal prefill path. It is a single call. If it fails, it returns `ENTROPIC_ERROR_GENERATE_FAILED` with an error message. It is not retried either.

**What the caller receives on failure**

`LlamaCppTokenizer::tokenize` returns an empty vector and logs at error level with the input length. `LlamaCppBackend::tokenize` (`llama_cpp_backend.cpp:788`) forwards that empty vector. It also returns an empty vector when `tokenizer_` is null. The error is never propagated as a code or exception. An empty vector is the only signal.

Two gaps in the first call:
- If the first call returns a real error rather than a size, `n = -n` treats it as a size and allocates from it. I did not verify the pinned llama.cpp return contract for error cases, so I can't say how likely this is.
- The `actual < 0` branch is only reached if the second call disagrees with the first. I did not check whether that can happen in practice.

**What the callers do with the empty vector**

| Caller | Behaviour on empty tokens | Result |
|---|---|---|
| `do_generate_text_only` (`:2561`) | No check. Logs "0 input tokens", then prefills. `run_prefill` (`:1484`) loops over zero tokens and returns true. | Generation runs on an unprimed context. I did not trace `generate_after_prefill` to see what it samples from. |
| `do_complete` (`:3947`) | No check. Passes the empty vector to `decode_loop`. | Same as above. |
| `do_generate_batch` (`:1911`) | No check. `batch_shared_prefix_len` returns 0 for an empty sequence (`batch_util.h:43`). | Batch proceeds with an empty prompt. |
| Speculative (`:3593`) and MTP (`:3921`) | Checks `tokens.size() < 2`. | Returns an error, but the message says "must have at least 2 tokens", not "tokenization failed". The real cause is only in the tokenizer's log. |
| `compute_prefix_token_count` (`:2066`) | No check. | Prefix length reported as 0. |
| `do_count_tokens` (`:825`) and `count_tokens` | No check. | Returns 0. |
| `entropic_inference_count_tokens` (`inference_c_api.cpp:548`) | Only exceptions fall back to `len/4`. | Returns 0, indistinguishable from an empty string. |

The main problem is the count path. A failed exact count returns 0 with no signal, so a caller cannot tell a tokenizer failure from empty input. The generate paths have the same ambiguity, and only the speculative and MTP paths catch it, with a misleading message.

I didn't change any code. If you want, the next step is to make `LlamaCppTokenizer::tokenize` report failure explicitly (an error code or `std::optional`), have the generate paths reject empty prompts, and fix the "sized retry" comments. That would touch the public seam signature, so it needs your sign-off first.