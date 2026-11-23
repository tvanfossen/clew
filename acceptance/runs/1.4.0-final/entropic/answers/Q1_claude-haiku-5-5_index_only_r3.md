**Why it calls llama.cpp twice:** the two calls are not in two places. Both `llama_tokenize` calls are in `entropic::LlamaCppTokenizer::tokenize` (`src/inference/llama_cpp_tokenizer.cpp:49-71`, external calls at lines 55 and 61). It's a two-phase buffer sizing pattern, not retry logic:

1. The first call passes a null output buffer and size 0. Per the body's comment, a negative return is the required token count, so the code negates it (`n = -n`).
2. It allocates a vector of that size and calls again to fill it.

I'd call this sizing, not retry. Nothing is re-attempted after a failure. The only failure branch is the second call returning negative, which logs an error and returns empty. The index shows no other `llama_tokenize` call sites.

**What the caller receives on failure:** an empty `std::vector<int32_t>`. There is no status, exception, or error code on this path. The same empty result comes back when `vocab_` is null, so the caller can't distinguish failure from empty input. The chain I could trace:

| Layer | On failure | Source |
|---|---|---|
| `LlamaCppTokenizer::tokenize` | `{}` plus `logger->error` | `llama_cpp_tokenizer.cpp:62-66` |
| `LlamaCppBackend::tokenize` | passes through `{}`; also `{}` when no tokenizer is wired | `llama_cpp_backend.cpp:788-800` |
| `tokenize_text` | `{}` | `llama_cpp_backend.cpp:837-841` |
| `do_count_tokens` | `0` | `llama_cpp_backend.cpp:825-828` |
| `InferenceBackend::count_tokens` | `0` when loaded; `len/4` estimate when not | `backend.cpp:496-501` |
| `entropic_inference_count_tokens` (C API) | `0`; the `len/4` fallback runs only on a thrown exception, which this path doesn't throw | `inference_c_api.cpp:548-562` |

**What the callers do with it:**

- **`do_complete`** (`llama_cpp_backend.cpp:3941-3955`) logs "N input tokens" and passes the empty vector straight to `decode_loop`. There is no check for empty input. I could not read `decode_loop`, so I don't know whether it errors or generates from nothing.
- **`do_generate_batch`** (`llama_cpp_backend.cpp:1903-1923`) takes the batch fast path or falls back to the serial path, with no check for empty token vectors in between. Whether an empty request is safe depends on `batch_shared_prefix_len` and `run_batched_decode`, which I did not inspect.
- **`compute_prefix_token_count`** returns `0`, which reads as "no system prefix."
- **`entropic_inference_count_tokens`** returns `0` to C API consumers, who cannot tell it from a genuinely empty string.

**Bottom line:** a tokenization failure is silent to every caller. The only signal is one `logger->error` line in `LlamaCppTokenizer`. The caller sees an empty token list or a count of zero, and downstream code does not check for either. If you want failures visible, the seam would need to return a status (or `std::optional`/`expected`) so the backend can reject the request instead of generating from an empty prompt. Changing that touches the `Tokenizer` interface, which is in the immutable-interface set under the repo's CLAUDE.md, so it would need a proposal first.