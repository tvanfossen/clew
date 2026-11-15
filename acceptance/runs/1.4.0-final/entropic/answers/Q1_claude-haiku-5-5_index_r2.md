## Why it calls `llama_tokenize` twice

The two calls in `LlamaCppTokenizer::tokenize` (`src/inference/llama_cpp_tokenizer.cpp:55` and `:61`) are a size query followed by the real call. llama.cpp's `llama_tokenize` returns the negative of the required token count when the buffer is too small, and it can't allocate the output for you. So the first call passes `nullptr, 0` to learn `n`, the code sizes a `std::vector`, and the second call fills it. Both calls always run; nothing is retried.

The second place is `LlamaCppTokenizer::detokenize` (`:93` and `:99`), which calls `llama_token_to_piece`. That one is closer to a retry, because the second call happens only when the 256-byte stack buffer is too small. It is still a size-on-demand fallback, not a retry after failure.

Neither is retry logic. Neither retries on error, and there is no backoff, no attempt counter, and no retry on a transient failure.

## What the caller receives on failure

`tokenize` has no error channel, so failure is signalled as an empty vector. That happens in three cases:

- `vocab_` is null (`:52`), which returns `{}` without logging.
- The sized call returns negative (`:64`). This is the only path that logs (`logger->error`, with the text length only).
- The wrapper has no tokenizer wired. `LlamaCppBackend::tokenize` returns `{}` (`llama_cpp_backend.cpp:796`).

`detokenize` returns `""` on the same kind of failure, also with no log.

An empty vector means "failed" and "legitimately zero tokens" at the same time. Empty text with `add_special=false` is a valid zero-token result, so the caller cannot tell them apart.

## What the callers do with it

```
llama_tokenize fails
  -> LlamaCppTokenizer::tokenize returns {}     (logs error, one line)
  -> LlamaCppBackend::tokenize returns {}
      |- do_count_tokens       -> 0
      |   -> InferenceBackend::count_tokens -> 0
      |   -> entropic_inference_count_tokens -> 0   (C API: no error signal)
      |
      |- do_complete           -> decode_loop({})
      |   -> run_prefill({})  : clears KV, decodes nothing, returns true
      |   -> sampling starts with no prompt; result is not marked as an error
      |
      |- do_generate_text_only -> run_prefill_cached({}) -> same as above
      |- compute_prefix_token_count -> 0 (cache keyed on an empty prefix)
      `- tokenize_text         -> empty vector to the caller
```

Points to note:

- **Counting** returns 0 to the C API caller, which is indistinguishable from a real empty count. The C API's `catch (...)` fallback to `len/4` never runs, because `tokenize` does not throw.
- **Generation** is the serious case. An empty prompt does not stop generation. `run_prefill` with zero tokens is a no-op after clearing memory, and it returns `true`. Decode then samples from whatever state the context is left in, and the result has no error code. I read this from the code and did not run it, so treat the exact behaviour as inferred.
- The only observable signal is one `logger->error` line in the tokenizer, and only on the sized-call failure path.

I did not check whether any test exercises the failure path through the backend, so I can't say whether this behaviour is covered. The mock tokenizer in `tests/unit/inference/tokenizer_seam_test.cpp` is the place to look.

## Possible next steps

If you want this fixed, the smallest change is to make failure explicit: return an `expected`-style result or an error flag from `Tokenizer::tokenize`, and have `do_complete` and `do_generate_text_only` return an error result instead of decoding an empty prompt. That changes the `Tokenizer` interface, which the project's CLAUDE.md treats as a design change, so it needs your sign-off first.