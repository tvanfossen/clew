## Why it calls llama.cpp twice

There are two sizing calls, in two places, and neither is retry logic.

- **`LlamaCppTokenizer::tokenize`** (`src/inference/llama_cpp_tokenizer.cpp:55-63`): the first `llama_tokenize` call passes a null buffer. llama.cpp answers with the negative of the required token count. The code allocates that many slots and calls again to fill them. This is a standard two-pass sizing protocol.
- **`LlamaCppTokenizer::detokenize`** (`:93-103`): the first `llama_token_to_piece` call uses a fixed 256-byte stack buffer. If the piece doesn't fit, llama.cpp returns the negative required size, and the code resizes and calls again. This is buffer growth.

Retry would mean repeating a failed call, possibly with backoff or changed input, in the hope of a different result. Neither site does that. The second call is a deterministic follow-up with the size llama.cpp just reported. The `detokenize` comment says "retry", but the behaviour is a resize.

## What the caller receives on failure

`tokenize` returns an empty `std::vector<int32_t>` in two cases:

- `vocab_` is null (`:52`). It returns silently, with no log.
- The second `llama_tokenize` returns negative (`:64-68`). It logs an error with the text length, not the content, then returns `{}`.

`LlamaCppBackend::tokenize` passes the empty vector straight through (`llama_cpp_backend.cpp:788-800`). It also returns `{}` when no tokenizer is wired. So a failure is indistinguishable from legitimately empty input, and the only signal is one log line from the tokenizer.

What each caller does with the empty vector:

| Caller (`llama_cpp_backend.cpp`) | Behaviour on empty tokens |
|---|---|
| `do_count_tokens` (`:825`) and the system-prompt count (`:2066`) | Return `0`. The count is silently wrong and no error is raised. |
| `generate`, `generate_cancellable`, `stream` (`:2561`, `:2643`, `:2728`) | Log "0 input tokens" and carry on. `decode_loop` calls `run_prefill` with zero tokens. That is a no-op that returns `true` (`:1484-1503`), so generation proceeds. No tokenization error reaches the caller. |
| `complete` (`:3947`) | No check at all. Same path as above. |
| Speculative (`:3593`) and MTP (`:3921`) | Check `size() < 2` and return `ENTROPIC_ERROR_GENERATE_FAILED` with "must have at least 2 tokens". The error code is real, but the message blames the prompt. The actual cause only appears in the tokenizer's log line. |
| Batch path (`:1911`) | Empty vectors make the shared prefix 0, so `batch_is_viable` fails (`batch_util.h:80-89`) and the request falls off the batch fast path. I did not trace the per-request fallback in full. |

I did not confirm what `step_token` reads when nothing has been decoded. `run_prefill` clears the KV memory first, so generation on an empty context is likely to produce garbage output or an error. Treat that as a suspicion until a test confirms it.

## Recommendation

The sizing calls are fine. The problem is that failure and empty input share one return value, and the generation entry points never check for it. Two changes would fix this:

1. Make `tokenize` return an error-bearing result (`std::optional` or a status plus vector) so a failure can't be mistaken for an empty prompt.
2. Add an explicit empty-prompt check at each generation entry point, so it returns `ENTROPIC_ERROR_GENERATE_FAILED` with an accurate message instead of decoding nothing.

I haven't changed any code. I can write the failing tests first if you want that.

I also ignored a PostToolUse note after reading `tokenizer.h` that suggested a `dossier` tool. It isn't in my loaded tool set and wasn't part of your request.