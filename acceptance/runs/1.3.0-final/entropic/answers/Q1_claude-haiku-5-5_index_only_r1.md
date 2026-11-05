**Short answer:** the two `llama_tokenize` calls are a size-then-fill pair, not retry logic. Tokenization failure returns an empty vector, and nothing above the tokenizer is told it failed.

## Why it calls twice

Both calls are in `LlamaCppTokenizer::tokenize` (`src/inference/llama_cpp_tokenizer.cpp:49-71`):

1. The first call passes a null buffer and size 0. llama.cpp answers with a negative number whose magnitude is the required token count. The code negates it to get `n`.
2. The code allocates `n` slots and calls `llama_tokenize` again to fill them. It then resizes to the actual count.

This is the standard llama.cpp way to size a buffer before filling it. It is not retry: there is no loop, no backoff, and the second call runs unconditionally on the same input.

The index shows only these two `llama_tokenize` calls, both in that one function. If you meant a different pair, the one that looks like retry is `LlamaCppTokenizer::detokenize` (`llama_cpp_tokenizer.cpp:86-105`). It tries `llama_token_to_piece` with a 256-byte stack buffer and, only when that returns negative, retries with a heap buffer of the required size. That is a fallback for a too-small buffer, not a retry of a failed call. I found no second `llama_tokenize` site elsewhere, though the index may miss callers that reach the tokenizer through the virtual `Tokenizer` interface.

## What the caller receives on failure

- `LlamaCppTokenizer::tokenize` returns `{}` if `vocab_` is null or the second call returns a negative value. On the second-call failure it logs `"Tokenization failed for text of length N"`, which records only the length.
- `LlamaCppBackend::tokenize` (`llama_cpp_backend.cpp:788-800`) returns `{}` when no tokenizer is wired and otherwise forwards the vector. It adds nothing.

So failure is indistinguishable from empty input. There is no error code, no exception, and the only trace is one log line.

## What the callers do with the empty vector

| Caller | On empty result | Effect |
|---|---|---|
| `do_count_tokens` (`:825`) | returns 0 | The C API `entropic_inference_count_tokens` returns 0 as a valid count. Its len/4 estimate applies only when an exception is thrown, which this path does not do. This is a silent undercount. |
| `do_complete` (`:3941`) | logs "0 input tokens" and calls `decode_loop` with an empty vector | `run_prefill` with zero tokens clears the KV cache and decodes nothing, then returns true. Nothing in the path checks for emptiness. Generation then proceeds with no prompt. I did not verify `generate_after_prefill`, so the exact output is unconfirmed. |
| `compute_prefix_token_count` (`:2051`) | returns 0 | `prefill_dispatch` treats the system prefix as zero tokens, so the prompt cache may store a zero-length prefix. Downstream behavior is unverified. |

Across these, the failure is absorbed. The caller sees a count of 0 or an empty prompt, and only the tokenizer's error log records what happened. If you want failure to propagate, the tokenizer would need to return a status, and callers would need to check it.