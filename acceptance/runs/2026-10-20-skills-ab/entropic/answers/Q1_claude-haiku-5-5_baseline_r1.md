**Why it calls twice:** `LlamaCppTokenizer::tokenize` (`src/inference/llama_cpp_tokenizer.cpp:55` and `:61`) uses llama.cpp's two-phase sizing idiom. The first `llama_tokenize` call passes a null buffer and capacity 0, so it can only report the required count, returned as a negative number. The code negates it, allocates that many ids, and calls again to fill them. The comment at line 40 says the same thing.

`detokenize` (`:93` and `:99`) has the same shape. It tries a 256-byte stack buffer first and retries only if llama.cpp reports the buffer was too small.

**Is it retry logic?** No. There is no loop, no backoff, and no re-attempt after an error. The second call happens only because the first one reported a size, and it runs once. If the second call fails, the code logs and returns empty. The only retry-like behaviour is resizing a buffer after a size report. One weak spot: the first call's result is not checked for real errors. Its negative return is treated as a size, so a non-size failure there would become an allocation of that many ids. I did not verify whether llama.cpp can return that case.

**What the caller receives on failure:** an empty `std::vector` (`:64-67`), with an error logged that includes only the text length. There is no error code and no exception. The same empty vector is returned when `vocab_` is null (`:52`), and when the backend has no tokenizer wired (`llama_cpp_backend.cpp:795`). The interface doc (`tokenizer.h:48`) says "empty on failure or empty input", so the two cases cannot be told apart by the return value.

**What the callers do with it (`llama_cpp_backend.cpp`):**

```
llama_tokenize fails → tokenize() returns {}
  ├─ do_count_tokens (825)            → count reported as 0, silently
  ├─ compute_prefix_token_count (2066) → prefix count 0, silently
  ├─ do_generate_text_only (2561)     → logs "0 input tokens", continues to prefill
  ├─ do_generate_text_only stream (2728) → same
  ├─ do_complete (3947)               → same, no check
  ├─ do_generate_batch (1911)         → empty entry in the batch, no check
  ├─ speculative (3593)  → tokens.size() < 2 → error
  └─ MTP (3921)          → tokens.size() < 2 → error
```

- **Generation and completion paths** have no empty check. `run_prefill` (`:1484-1503`) with zero tokens skips the decode loop and returns `true`, so generation proceeds with an empty prompt. I did not trace the warm-keep prefill branch or the sampling loop after prefill, so I cannot say what those produce from an empty prompt.
- **Speculative and MTP paths** do check, but the check fires on `size() < 2`, and the error they return says the prompt "must have at least 2 tokens". The real cause, a tokenizer failure, is lost.
- **Counting paths** return 0, which callers cannot tell apart from an empty prompt.
- **Detokenize failures** return `""`, so a token that fails to render is dropped from output without any error (`:1534`, `:1819`).

The practical consequence is that a tokenizer failure does not surface as a tokenizer error anywhere above the seam. It shows up as a 0 count, an empty prompt, or a misleading "at least 2 tokens" message. The fix would be to change the seam to return a status (or throw inside the `.so` and convert at the C boundary) so callers can tell failure from empty input. That is an interface change under the project's rules, so it needs your approval first.

This was a read-only investigation. I did not build or run tests.