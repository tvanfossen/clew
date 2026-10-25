**Short answer:** neither spot is retry logic. Both are size-probing. The tokenizer asks llama.cpp how big a buffer it needs, then fills one. A failed tokenization is not retried, and the caller gets an empty vector.

## Why it calls twice

The two sites are in `src/inference/llama_cpp_tokenizer.cpp`, in two different functions:

| Site | Calls | Second call happens when | Purpose |
|---|---|---|---|
| `LlamaCppTokenizer::tokenize` (`:55`, `:61`) | `llama_tokenize` twice | Always | First call with a null buffer returns the negative required token count. Second call fills a vector of that size. |
| `LlamaCppTokenizer::detokenize` (`:93`, `:99`) | `llama_token_to_piece` up to twice | Only if the 256-byte stack buffer is too small | Same probe pattern, with a stack buffer first and a heap resize only when needed. |

Retry would mean "try again because the first attempt failed." Neither site does that. The detokenize resize is conditional, so it is the closer of the two, but it is still a resize, not a retry. The tokenize path always makes two calls, and the code never tries again on any failure. Only the second call's negative return is checked (`:64`).

## What the caller receives on failure

```
llama_tokenize fails (2nd call < 0)
  └─ LlamaCppTokenizer::tokenize   logs error (length only), returns {}
      └─ LlamaCppBackend::tokenize  passes {} through (also {} if tokenizer_ is null)
          ├─ do_count_tokens                   → 0
          │    └─ entropic_inference_count_tokens → 0 (C API)
          ├─ do_complete / do_generate_* / generate_mtp / generate_speculative_with_draft
          │    → tokens.size() == 0 → logs "0 input tokens"
          │    → run_prefill_cached(empty) → run_prefill loops zero times, returns true
          └─ compute_prefix_token_count → 0
```

Points about this chain:

- **Failure and empty input look the same.** `Tokenizer::tokenize` documents the return as "empty on failure or empty input" (`include/entropic/inference/tokenizer.h:48`). Nothing downstream can tell them apart.
- **The error is not surfaced.** The only signal is one `logger->error` line in the tokenizer. The caller gets no status, and the generation path does not return an error code.
- **The C API fallback never fires.** `entropic_inference_count_tokens` returns `len/4` only when `count_tokens` throws (`inference_c_api.cpp:548`). Tokenizer failure returns `{}` rather than throwing, so the caller sees `0`.
- **Generation proceeds with an empty prompt.** `run_prefill` treats zero tokens as success. The decode loop then runs without any prompt in context. I did not trace `step_token` on an empty context, so I can't say what it emits. This is the part to check first if you want to see the failure in practice.

## Recommendation

If you want failures to be visible, `LlamaCppTokenizer::tokenize` should return a status (or throw, which the C API already catches), and the generation entry points should reject an empty token vector for non-empty input. That is a change to the `Tokenizer` contract, so per the repo's rules it needs a design-decision entry. I have not made it.