**Short answer:** the two `llama_tokenize` calls are a size probe, not retry. Failure returns an empty vector, which callers can't tell apart from "no tokens," and one path turns that into a generation with no prompt.

**Why it calls twice**

Both calls are in `LlamaCppTokenizer::tokenize` (`src/inference/llama_cpp_tokenizer.cpp:49-71`). The index shows:

1. Line 55: `llama_tokenize(vocab_, text, ..., nullptr, 0, add_special, true)`. The output buffer is null, so llama.cpp can only report how many tokens it needs. The code reads that as a negative return and flips the sign (`if (n < 0) n = -n`).
2. Line 61: it allocates `n` slots and calls `llama_tokenize` again to fill them. The second return is the real count, and the vector is resized to it.

The first call is a probe. The second call is the real work. Nothing is re-attempted on the same input, so I wouldn't call this retry logic.

The "two different places" in the question are the two call sites, both in that one function. Above it, `LlamaCppBackend::tokenize` (`src/inference/llama_cpp_backend.h:788`) is a thin wrapper that forwards to `tokenizer_->tokenize`. It makes no llama.cpp call of its own.

**What the caller receives on failure**

`LlamaCppTokenizer::tokenize` returns `{}` in two cases:
- `vocab_ == nullptr`, silently, with no log.
- The second `llama_tokenize` returns negative. This path logs `"Tokenization failed for text of length {}"` and logs only the length, not the text.

The `Tokenizer::tokenize` contract says "empty on failure or empty input" (`include/entropic/inference/tokenizer.h:51`). So a caller can't distinguish failure from an empty string.

**What the callers do with it**

| Entry point | On empty result |
|---|---|
| `LlamaCppBackend::tokenize` | Returns `{}` when no tokenizer is wired. |
| `tokenize_text` (`add_special=true`) | Passes `{}` through. The doc says "empty if COLD or error." |
| `do_count_tokens` | Returns `0`. |
| `InferenceBackend::count_tokens` | Returns the exact count when loaded; `len/4` when COLD. |
| `entropic_inference_count_tokens` (C API) | Returns `0` for null handles or text, and `len/4` on exception. |
| `do_generate_text_only` (`llama_cpp_backend.cpp`, body at index lines 2555-2598) | Logs "0 input tokens" and keeps going. |

The generation path is the one that matters. In `do_generate_text_only`:
- `run_prefill_cached({})` is called with an empty vector.
- `run_prefill` (`llama_cpp_backend.h:1484-1503`) clears the KV memory, runs a loop that executes zero times, and returns `true`.
- Sampling then starts from a cleared context with no prompt. The result is not marked as an error. `error_code` is only set when a sampler step reports `"error"`.

So a tokenization failure on the generation path is not surfaced. It becomes a normal-looking generation with no prompt. The only trace is an error line in the log and a "0 input tokens" info line.

Caveats:
- I read these bodies from the index, not from source, and I did not check whether `do_generate` or `generate` has a guard before reaching `do_generate_text_only`. The index answers only for the functions I queried.
- The index doesn't include llama.cpp's own `llama_tokenize` contract, so the "negative return means required size" reading rests on the code's comment and the sign-flip logic, not on the llama.cpp header.