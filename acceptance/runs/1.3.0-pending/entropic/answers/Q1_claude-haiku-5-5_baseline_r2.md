**Short answer:** neither call is retry logic. Both are the standard two-step size-query pattern for C APIs, and the failure path is a silent empty vector.

## Why it calls twice

There are two sites, and they differ.

**1. `LlamaCppTokenizer::tokenize`** (`src/inference/llama_cpp_tokenizer.cpp:55-63`)

- Call 1 passes `nullptr` and a size of 0. llama.cpp answers with the negative of the required token count. This is a size probe, not an attempt that failed.
- Call 2 allocates `n` slots and makes the real call.
- The `if (n < 0) n = -n;` line is the only handling of the probe result.

The comment on line 44-45 calls call 2 "the sized retry," which is misleading. Nothing was retried.

**2. `LlamaCppTokenizer::detokenize`** (`llama_cpp_tokenizer.cpp:93-101`)

- Call 1 uses a fixed 256-byte stack buffer. If the piece is longer, llama.cpp returns the negative required size.
- Call 2 uses a heap buffer of that size.

This one is a real fallback for a too-small buffer, not a failure retry, and it does not fail for a transient reason.

So: a size probe followed by the real call, plus a buffer-growth fallback in detokenize. No backoff, no repeated attempt at the same operation, no retry of a failure.

## What the caller receives on failure

- `LlamaCppTokenizer::tokenize` logs an error with only the text length (line 65-66, which is the only log line on this path) and returns `{}`.
- `{}` is also what it returns for empty input and for a null vocab (lines 52, 44). Callers cannot tell "failed" from "empty."
- `LlamaCppBackend::tokenize` (`llama_cpp_backend.cpp:788-800`) returns `{}` when no tokenizer is wired too. The same vector means three different things.

Note that call 2 in the tokenizer can only fail if something other than the size is wrong. The sized call normally succeeds, so the `actual < 0` branch is defensive.

## What the callers do with it

Flow for the failure case:

```
llama_tokenize (fails)
  -> LlamaCppTokenizer::tokenize returns {}      (logs error, text length only)
  -> LlamaCppBackend::tokenize returns {}
  -> callers:
     a. tokenize_text / do_count_tokens  -> 0 or empty  -> count_tokens() = 0
     b. generate / generate_cancellable / stream / complete
          -> tokens.size() is 0, no check
          -> run_prefill(0 tokens): loop never runs, returns true
          -> sampling begins with no prompt decoded
     c. speculative / MTP paths
          -> tokens.size() < 2  -> returns ENTROPIC_ERROR_GENERATE_FAILED
```

Consequences:

- **Generation (b):** the plain generate and stream paths have no empty-token guard. I read `run_prefill` (`llama_cpp_backend.cpp:1484-1502`) and it reports success for zero tokens, so the failure becomes a silent bad generation instead of an error. This comes from reading the code. I did not run it against a model, so treat it as likely rather than confirmed.
- **Counting (a):** `entropic_inference_count_tokens` (`src/inference/inference_c_api.cpp:548-560`) returns 0 on tokenizer failure. Its doc comment promises a `text_len/4` estimate "on error," but that estimate is only used on the exception path. A caller budgeting context would see a zero-token prompt and could overfill the context.
- **Speculative/MTP (c):** these are the only paths that check the result, and they reject it with an error code.

## Recommended fixes (not applied; you asked a question, not for changes)

1. Have `Tokenizer::tokenize` report failure distinctly (e.g. an error out-parameter or `std::optional`) so empty input and failure can be told apart.
2. Add a guard in the generate and stream paths, matching the speculative/MTP `< 2` check, so failures return `ENTROPIC_ERROR_GENERATE_FAILED`.
3. Make `count_tokens` fall back to the `text_len/4` estimate on failure, as its doc comment already says.
4. Fix the misleading "sized retry" comment on line 44-45.