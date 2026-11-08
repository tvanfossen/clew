**Short answer:** the two calls are in one function, not two places, and it is a size-then-fill pattern rather than retry logic.

**Why it calls twice** (`src/inference/llama_cpp_tokenizer.cpp:55` and `:61`, in `LlamaCppTokenizer::tokenize`)

- The first `llama_tokenize` call passes a null buffer and size 0. llama.cpp reports the required token count as a negative number, which the code flips to positive.
- It allocates a vector of that size and calls `llama_tokenize` again to fill it.
- The second call is unconditional. Nothing loops, backs off, or re-tries on failure. If the second call returns a negative value, the function logs an error and returns empty.

The doc comment at line 45 says "the sized retry," which is misleading. It is a two-phase sizing call. A reviewer might reasonably call it "retry," but the code never re-attempts the same operation.

The same two-call pattern appears in `tests/model/test_gh87_common_chat_e2e.cpp:51` and `:56`. The backend's `mtmd_tokenize` call at `llama_cpp_backend.cpp:2407` is a different API and is not part of this.

**What the caller receives on failure**

A plain empty `std::vector<int32_t>`. There is no error code, no exception, and no status flag. The same empty result also comes back when `vocab_` is null, and when `tokenizer_` is unset in `LlamaCppBackend::tokenize` (`llama_cpp_backend.cpp:795`). An empty result is therefore indistinguishable from legitimately tokenizing an empty string. The only signal is one `error` log line.

**What the callers do with it**

| Caller | Behaviour on empty |
|---|---|
| `do_count_tokens` (`llama_cpp_backend.cpp:826`) | Returns `0`. A failed tokenization looks like a zero-token count. |
| Generate path (`:2561`) | Logs "0 input tokens" and proceeds to `decode_loop`. No check. |
| `do_complete` (`:3947`) | Same: proceeds with an empty prompt. |
| `do_generate_batch` (`:1911`) | Empty vector goes into the batch-planning arithmetic with no check. |
| System-prompt count (`:2066`) | Returns `0`. |
| MTP path (`:3921`) | The only caller that checks. `tokens.size() < 2` returns `GENERATE_FAILED` with "MTP prompt must have at least 2 tokens", which misreports the real cause. |
| `detokenize` consumers (`:1534`, `:1819`) | Empty string is appended silently. |

`run_prefill` (`llama_cpp_backend.cpp:1484`) with an empty vector clears the KV memory, makes no decode calls, and returns `true`. So a failed tokenization on the generate or complete path can reach a "successful" return with nothing processed.

**Not verified:** I did not trace how `decode_loop` handles an empty prompt, so I can't say whether generation then fails loudly or produces output from nothing. That is the first thing to check if you want to turn this into a fix. Making the failure explicit would mean returning a status alongside the vector, or having the callers treat an empty result from a non-empty input as an error.