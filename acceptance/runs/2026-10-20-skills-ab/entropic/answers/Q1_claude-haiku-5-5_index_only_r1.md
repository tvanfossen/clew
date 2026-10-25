**Short answer:** the double call is almost certainly a size-probe, not retry logic. I could not read the body of the function that makes it, so this rests on the index's doc text, not the code.

**Why it calls twice.** The index describes `LlamaCppTokenizer::tokenize` as returning empty "if `vocab_` is null or `llama_tokenize` returned a negative actual-count on the sized retry." That is the standard llama.cpp pattern: `llama_tokenize` returns a negative number when the output buffer is too small, and the magnitude is the required token count. The first call uses a guessed buffer. If it comes back negative, the code resizes to that count and calls again on the same input. Success is the normal path, and the second call only happens because the first buffer was too small.

**Is it retry logic?** No. Nothing failed on the first call in the sense of an error; the first call reports the size it needs. The same class's `detokenize` has a "retry decode" in its doc, which is similar, but I could not confirm the two call sites are exactly the ones you mean. The index shows no single place where a failed call is retried.

**Failure outward.** Tokenization failure returns an **empty vector**. The `LlamaCppBackend::tokenize` wrapper returns `{}` when no tokenizer is wired, so an unwired tokenizer and a failed tokenization look the same. The callers:

| Caller | What it does with empty |
|---|---|
| `do_count_tokens` | returns `0` (size of empty vector) |
| `Tokenizer::count_tokens` default | returns `0` |
| `compute_prefix_token_count` | returns `0`, so the system-prefix cache is sized to nothing |
| `do_complete` | passes empty to `decode_loop` with no check |
| `do_generate_text_only`, `do_generate_streaming_text_only` | no check; logs "0 input tokens", then `run_prefill_cached` |
| `generate_mtp` | the only one that checks: `tokens.size() < 2` returns "MTP prompt must have at least 2 tokens", a misleading message for a tokenizer failure |

`run_prefill` with zero tokens clears the KV cache and returns `true`, because its loop never runs. So on the text-only paths a tokenizer failure does not produce `prefill_error()` (the `"Prefill decode failed"` result). It passes through to generation with an empty prompt. What happens next depends on `step_token` and the decode loop, which I could not inspect.

**Bottom line.** The tokenizer-to-caller boundary has no error channel. Failure is reported as "zero tokens", which the callers treat as a valid count or a valid empty prompt. Only the MTP path rejects it, and then with the wrong explanation. If you want this fixed, the seam needs a distinct failure signal (a status or `std::optional`) instead of an empty vector. To confirm the retry shape and the detokenize path, the source of `src/inference/llama_cpp_tokenizer.cpp` needs a read; the index does not hold its body.