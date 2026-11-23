**Why it calls twice: sizing, not retry.** `LlamaCppTokenizer::tokenize` (`src/inference/llama_cpp_tokenizer.cpp:49-71`) calls `llama_tokenize` at lines 55 and 61. The first call passes a null buffer and size 0. llama.cpp returns the negative of the token count it would need, and the code flips the sign to size the vector. The second call fills that vector. The first call is a query, not an attempt that failed. I would not call it retry logic.

The other pair is in `LlamaCppTokenizer::detokenize` (`llama_cpp_tokenizer.cpp:86-105`), which calls `llama_token_to_piece` at lines 93 and 99. That one is closer to retry: it tries a 256-byte stack buffer, and if the piece doesn't fit, it retries once at the exact size llama.cpp reported. It is still a single size-on-demand retry, not a loop. The index only has the source line numbers for these calls; I did not verify llama.cpp's return contract beyond what the code comments and call pattern imply.

**What the caller receives on failure.** Two things can fail, and both collapse to an empty vector:

- `vocab_` is null → `{}` (`llama_cpp_tokenizer.cpp:51`).
- The fill call returns negative → logs an error with the text length, then returns `{}` (`llama_cpp_tokenizer.cpp:63-66`). The text itself is not logged, and the sizing-call result is not checked.

`LlamaCppBackend::tokenize` (`llama_cpp_backend.cpp:788-800`) returns `{}` if `tokenizer_` is unset, and otherwise passes the seam's result through. There is no status code, so the empty vector is the only signal.

**What the callers do with the empty vector.** The index shows no error check at any of these sites:

| Caller | What happens with `{}` |
|---|---|
| `do_count_tokens` (`:825`) | Returns `0`. The `count_tokens` C API (`inference_c_api.cpp:548-562`) returns that `0` unchanged. A caller cannot distinguish "empty text" from "tokenizer failed," and the `len/4` fallback only applies to exceptions. |
| `do_complete` (`:3941`) | Logs "0 input tokens" and passes the empty prompt to `decode_loop`. `decode_loop` (`:1562`) only checks `run_prefill`, not the token count. |
| `do_generate_text_only` (`:2555`) | Same: logs 0 tokens, then calls `run_prefill_cached` with the empty vector. |
| `compute_prefix_token_count` (`:2051`) | Returns `0`, which the prefix accounting treats as "no system prefix." |
| `tokenize_text` (`:837`) | Returns an empty vector. Its interface doc says "empty if COLD or error," so callers have no way to tell the two apart. |

**Bottom line.** A tokenization failure is logged once and then becomes a silent empty prompt. The caller can end up decoding nothing, or report a zero token count, without any error propagating. The one caller that does check for an error is `decode_loop`, but only for prefill failures, and an empty prompt is not a prefill failure. I did not read the bodies of `run_prefill` or `InferenceBackend::count_tokens` (the wrapper in `backend.h`), so I can't say whether an empty token vector trips a later check there.