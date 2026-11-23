**Short answer:** the two calls are not in two different places. Both `llama_tokenize` calls are in `LlamaCppTokenizer::tokenize` (`src/inference/llama_cpp_tokenizer.cpp:49-71`, calls at lines 55 and 61). The second call is not retry logic.

## Why it calls twice

llama.cpp's `llama_tokenize` has a sizing convention: called with a null buffer, it returns the negative of the token count it needs. So the code does:

1. **Probe:** `llama_tokenize(vocab, text, nullptr, 0, ...)`. A negative result is flipped to a positive size `n`.
2. **Fill:** allocate `n` slots and call `llama_tokenize` again with the buffer.
3. **Check:** if the fill returns negative, log `"Tokenization failed for text of length N"` and return `{}`. Otherwise resize to `actual` and return.

Retry means running the same operation again because the first attempt failed. Here the second call runs unconditionally after the probe succeeds. It is a two-pass size-then-fill pattern, and a failure on the second pass is final.

## What the caller receives on failure

The failure becomes an **empty `std::vector<int32_t>`**. The same empty vector also means "empty input" and "vocab is null", which the code handles silently with no log. Nothing is thrown, and no error code is set at this layer. The `Tokenizer::tokenize` doc says "empty on failure or empty input", so the interface itself does not separate the two cases.

The empty vector then propagates through `LlamaCppBackend::tokenize` (`llama_cpp_backend.cpp:788-800`), which returns it unchanged. Callers in the index:

| Caller | What it does with the empty result | Visible effect |
|---|---|---|
| `do_count_tokens` | returns `size()` | returns **0**, same as a real zero-token string |
| `compute_prefix_token_count` | returns 0 | prefix length 0, which feeds the prompt-cache path |
| `tokenize_text` (public API) | returns the empty vector | the doc says "empty if COLD or error", so the caller cannot tell them apart |
| `do_complete` | logs "0 input tokens", calls `decode_loop` | no error set on this path |
| `do_generate_text_only` | passes empty tokens to `run_prefill_cached` | no error set on this path |
| `do_generate_batch` | feeds empty token lists into the shared-prefix logic | no error set on this path |

The main risk is in `do_complete` and `do_generate_text_only`. `run_prefill` with zero tokens clears the KV memory and then decodes nothing, and it returns `true`. So a tokenization failure can turn into generation from an empty prompt with a success-shaped result. The only trace is the one `logger->error` line in the tokenizer.

## What I did not verify

- `generate_after_prefill`, `run_prefill_cached`, and `batch_shared_prefix_len` are not read, so the exact behavior for an empty prompt there is inferred, not confirmed.
- I did not check whether any caller above the C API checks for an empty prompt before reaching the backend.
- My search for `llama_tokenize` call sites returned a capped list of 25 results. The dossier for `LlamaCppTokenizer::tokenize` lists `llama_tokenize` as its only external callee, and nothing in the index suggests another call site, but I did not enumerate them all.