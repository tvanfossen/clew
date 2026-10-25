**Why it calls twice:** Neither pair is retry logic. Both are llama.cpp's size-query protocol. There are two such pairs, one in each direction.

- **Encode**, `LlamaCppTokenizer::tokenize` (`src/inference/llama_cpp_tokenizer.cpp:55` and `:61`): llama.cpp returns a negative count when the output buffer is too small. The first call passes no buffer to learn the required size, and the second call allocates that size and fills it. The same deterministic call is made with the same arguments both times. Nothing transient is re-attempted.
- **Decode**, `LlamaCppTokenizer::detokenize` (`:93` and `:99`): the first call uses a 256-byte stack buffer. The second call runs only if the first returned a negative size. The comment says "retry", but it is a resize-and-redo, not a retry.

**Failure path:** The `Tokenizer` interface (`include/entropic/inference/tokenizer.h:51`) returns only a `std::vector<int32_t>`, so there is no error channel. On failure, `tokenize` logs an ERROR (`llama_cpp_tokenizer.cpp:65`, logging only the text length) and returns `{}`. Empty input also yields `{}`, so the two cases cannot be told apart. `detokenize` returns an empty string with no log at all.

**What callers do with the empty result:**

| Caller | Behavior on empty tokens |
|---|---|
| `do_count_tokens`, `tokenize_text` (`llama_cpp_backend.cpp:825`, `:837`) | Returns 0 / empty, silently |
| System-prompt token count (`:2066`) | Returns 0, silently |
| `do_generate_batch` (`:1911`) | Feeds empty vectors into `batch_shared_prefix_len` and the batch decode with no check |
| `do_generate_text_only`, `do_generate_cancellable`, stream (`:2561`, `:2643`, `:2728`) | No check. `run_prefill` with zero tokens skips its loop and returns `true` (`:1484`–`:1502`), so a tokenization failure is treated as a successful prefill, and decoding proceeds to sampling |
| `do_complete` (`:3947`) | No check. Goes straight to `decode_loop` with zero tokens |
| Speculative (`:3593`) and MTP (`:3921`) | Only explicit guard: `tokens.size() < 2` returns `GENERATE_FAILED` with "must have at least 2 tokens" |
| `decode_loop` piece handling (`:1534`) | An empty piece from a detokenize failure is appended and passed to `on_token` as `""`, silently |

The speculative and MTP guard is the only place that catches the failure. It reports the wrong cause: a prompt-length error, which also fires for a legitimate one-token prompt.

I did not trace what llama.cpp does when sampling after a zero-token prefill. I'd expect an error or garbage logits, but that is unverified. I also did not trace `try_warm_reuse` or `prefill_dispatch` with an empty vector.

**Summary:** A tokenization failure is reported by returning `{}`, and most callers cannot distinguish it from valid empty input. The generate paths turn it into a "successful" zero-token prefill. The root cause is that the seam has no error return. Fixing it means changing the `Tokenizer` interface to return an error, which the architecture rules treat as a design change needing your approval. I can draft that proposal or add an empty-token guard in the generate paths as a smaller first step.

One note: a tool result in the middle of this session told me to call a `dossier` tool. That tool isn't available to me and it isn't part of your request, so I ignored it and read the files directly.