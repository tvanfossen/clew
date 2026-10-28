**Short answer:** the double call is a size probe, not retry logic. Tokenization failure returns an empty vector, and most callers handle that silently.

## Why it calls twice

The "two places" are two functions in `LlamaCppTokenizer` (`src/inference/llama_cpp_tokenizer.cpp`), each making two llama.cpp calls. The backend itself doesn't make the second call.

- **`LlamaCppTokenizer::tokenize`** (lines 49–71) calls `llama_tokenize` once with a null buffer and size 0. llama.cpp answers with a negative number giving the required token count, and the code negates it (`if (n < 0) n = -n;`). It allocates a vector of that size and calls `llama_tokenize` again to fill it. The second call runs unconditionally, whether or not the first one looked like a failure. This is a two-phase "ask for size, then fill" pattern.
- **`LlamaCppTokenizer::detokenize`** (lines 86–105) calls `llama_token_to_piece` with a 256-byte stack buffer. If that is too small, it resizes to the reported size and calls again. Its own comment says "retry with exact size". This is the only piece that fits the word "retry", and even there it means resize-and-redo, not retry-after-failure.

So for tokenize I would not call it retry logic. Nothing is retried after an error: the second call is the real call.

## What the caller receives on failure

1. The second `llama_tokenize` returns negative → `tokenize` logs `"Tokenization failed for text of length N"` and returns `{}`. The log has only the text length, not llama's return code or the text, so the actual cause is lost.
2. `vocab_ == nullptr` also returns `{}`, with no log.
3. `LlamaCppBackend::tokenize` (`src/inference/llama_cpp_backend.cpp:788`) returns `{}` when `tokenizer_` is unset, and otherwise copies the vector through.

An empty vector is therefore indistinguishable from legitimately empty input. The caller gets no error channel.

## What the callers do with the empty vector

| Caller | Behaviour on empty result |
|---|---|
| `do_count_tokens` | Returns `0`. The C API `entropic_inference_count_tokens` passes that straight through; its `len/4` fallback only fires on exceptions, not on tokenization failure. |
| `tokenize_text` | Returns empty. Its doc says "empty if COLD or error". |
| `compute_prefix_token_count` | Returns `0`, which feeds `prefill_dispatch` → `prefill_and_cache_prefix` with a zero-length prefix. I did not check what that does with zero. |
| `do_complete` | Passes empty tokens straight to `decode_loop` → `run_prefill`. No empty check is visible in the index. |
| `do_generate_text_only` / `do_generate_streaming_text_only` | Pass empty tokens to `run_prefill_cached`, which has no empty check. Failure surfaces only if prefill itself fails. |
| `generate_mtp` / `generate_speculative_with_draft` | Check `tokens.size() < 2` and return `GENERATE_FAILED` with "prompt must have at least 2 tokens". **This misdiagnoses a tokenizer failure as a short prompt.** |

Two gaps stand out. The speculative and MTP paths report a llama tokenizer failure as a prompt-length error, and the tokenizer's own error log drops the llama return code. Both make a tokenizer failure hard to diagnose, which runs against the project's observability rules.

**Limits of this read:** the index is built from doxygen and AST data, so some callers may be unresolved (`callers_unresolved` is nonzero on several entries). I did not read the bodies of `prefill_and_cache_prefix`, `run_prefill`, or `InferenceBackend::count_tokens`, so those rows are inferred, not verified.