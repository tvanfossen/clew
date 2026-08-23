Now I have the full picture, top to bottom.

## Why two calls, and is it retry logic?

Both `LlamaCppTokenizer::tokenize` and `::detokenize` (`src/inference/llama_cpp_tokenizer.cpp:49-105`) call the underlying llama.cpp function twice, but it's the **standard llama.cpp two-pass sizing idiom**, not retry logic:

- **`tokenize`**: call 1 passes `nullptr, 0` as the output buffer — llama.cpp can't write anything, so by contract it returns `-required_size`. The code negates that to size a `std::vector<int32_t>`, then calls a **second time** with a correctly-sized buffer to actually get the token ids.
- **`detokenize`**: inverted order — call 1 optimistically uses a 256-byte stack buffer (fast path, works for the overwhelming majority of pieces). Only if that returns negative (buffer too small) does it fall back to a second call sized exactly from `-n`.

Retry logic implies "the same call might succeed on a second attempt after failing" — recovering from a transient condition. That's not what's happening here: the first call is a **deliberate query for the size needed**, and the second call's success is deterministic given the first call's answer (short of vocab corruption). There's no backoff, no bounded attempt count, no transient-failure assumption — it's a two-phase protocol (measure, then fill), which is a common C API pattern when you can't know an output size ahead of time. I'd call it a **sizing/probe pattern**, not retry logic.

## What happens on failure, traced outward

**At the seam (`llama_cpp_tokenizer.cpp`):**
- `tokenize`: if `vocab_` is null, or the second (sized) call returns negative, the function logs an error and returns `{}` — an **empty vector**, indistinguishable from tokenizing an actually-empty string.
- `detokenize`: if `vocab_` is null, or the second call returns `≤0`, it returns `std::string{}` — an **empty string**, indistinguishable from a token that legitimately decodes to nothing (special tokens with `special=false`).

**One level up (`LlamaCppBackend::tokenize`/`detokenize`, `llama_cpp_backend.cpp:788-816`):** pure pass-through. No tokenizer wired → `{}`; tokenizer present but returns `{}` on failure → still just `{}`. The doc comment even says explicitly: *"matches the prior failure-path return shape"* — i.e., failure was never distinguished from "empty" even before this seam existed.

**At every caller in the backend** (`do_generate_text_only`, `do_complete`, `do_count_tokens`, `tokenize_text`, the batch/system-prompt paths, etc.) — I checked all of them and there is **no `tokens.empty()` / `ids.empty()` guard anywhere** in this file. An empty vector from a tokenization failure is treated identically to an empty vector from an empty prompt:

- `do_count_tokens` reports **0 tokens**, silently.
- `do_generate_text_only` / `do_complete` log `"0 input tokens"` and proceed straight into `run_prefill_cached` → `try_warm_reuse`/`run_prefill`/`prefill_dispatch`, which will attempt an `llama_decode` with `n_tokens == 0` rather than surfacing a tokenization error.
- `detokenize` failures during streaming (`step_token`, the `for (llama_token t : s.out) { r.content += detokenize(t); }` loop) just append nothing to the output text — a dropped token renders as silently missing text, not an error.

**Bottom line:** the two llama.cpp calls are a sizing probe, not retries. But the actual failure-propagation gap is the real finding — `tokenize`/`detokenize` collapse "failed" and "legitimately empty" into the same sentinel value (`{}`/`""`) at the seam, and nothing downstream re-distinguishes them. A real tokenization failure (e.g., a null/corrupted vocab, or a negative return from the sized call) is currently indistinguishable from the user sending an empty string — it doesn't error, it just quietly generates from zero tokens or decodes a gap in the output text.
