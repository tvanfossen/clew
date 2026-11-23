**Short answer:** The two calls are both `llama_tokenize` inside `LlamaCppTokenizer::tokenize` (`src/inference/llama_cpp_tokenizer.cpp:55` and `:61`). It is a size-then-fill pattern, not retry logic. On failure, the caller gets an empty token vector, and most callers never check for it.

**Why it calls twice**

llama.cpp's `llama_tokenize` takes an output buffer and its capacity. If the buffer is too small, it returns a negative number whose magnitude is the required token count. The code uses this:

1. First call passes `nullptr, 0`. It always fails with a negative return, which carries the needed size. The code negates it to get `n`.
2. It allocates `std::vector<int32_t>(n)`.
3. Second call passes the buffer. A non-negative `actual` is the real count; the vector is resized to it.

Two things make this not retry:
- The second call is not conditional on the first failing. It is the expected step.
- Nothing is repeated on failure: no loop, no backoff, no second attempt with the same arguments.

One wrinkle: a genuine llama.cpp error also returns negative, so the first call cannot tell "needs N" from "broke." The code treats both as a size. A real error then surfaces when the second call returns negative, which is the only place it is logged.

**Where the other llama.cpp call is**

The only other llama.cpp tokenization is `mtmd_tokenize` at `src/inference/llama_cpp_backend.cpp:2407`, in `mtmd_prefill`. It is a single call, and its failure is handled properly: it returns `ENTROPIC_ERROR_GENERATE_FAILED` with an error message. That is the contrast to the text path below.

**What the caller receives on failure**

`LlamaCppTokenizer::tokenize` logs at ERROR (text length only) and returns `{}`. Nothing else is signalled. The chain upward:

| Caller | On failure it gets | What it does |
|---|---|---|
| `LlamaCppBackend::tokenize` (`llama_cpp_backend.cpp:788`) | `{}` (also `{}` if no tokenizer is wired, with no log) | Passes it through |
| `do_count_tokens` (`:825`) | `0` | Returns 0 |
| `InferenceBackend::count_tokens` → `entropic_inference_count_tokens` (`inference_c_api.cpp:548`) | `0` | Returns 0 to the C caller |
| `tokenize_text` (`:837`) | empty vector | Passes it through |
| `do_generate_text_only` (`:2561`), cancellable (`:2643`), streaming (`:2728`), `do_complete` (`:3947`), batch (`:1911`) | empty `tokens` | No empty check. Logs "0 input tokens" and continues into `decode_loop`/`run_prefill` |
| `run_prefill` (`:1484`) | returns `true` with zero tokens decoded | The loop does not run |
| Speculative (`:3594`) and MTP (`:3922`) | `ENTROPIC_ERROR_GENERATE_FAILED` | Only callers that check, via `tokens.size() < 2`. The message says "must have at least 2 tokens" and hides the real cause |
| System-prompt prefix count (`:2066`) | `0` | Returns 0 |

**What this means**

- **Count callers cannot tell failure from an empty input.** A failed tokenization and an empty string both return `0`. The C header's Doxygen says "estimate on error" (`len/4`), but that only happens if an exception is thrown. A tokenize failure returns `0`, so the docs are wrong here.
- **Generation callers continue silently.** The plain generate, cancellable, streaming, and complete paths have no empty-token guard. Prefill then decodes nothing and reports success, so sampling runs without having processed a prompt. I did not verify what `generate_after_prefill` does with no logits. It is the likely source of garbage output or a confusing failure, and it needs a test that passes an unencodable prompt through `do_complete` or `do_generate_text_only` to confirm.
- **The fix is small.** Check `tokens.empty()` right after each `tokenize` call in the generation paths and return `ENTROPIC_ERROR_GENERATE_FAILED` with a clear message. The count path should either return an error code or document that `0` means failure. The mtmd path already shows the pattern.

I did not open the llama.cpp header in this repo to confirm the negative-return contract. It is taken from llama.cpp's documented behaviour and matches how the code uses it.