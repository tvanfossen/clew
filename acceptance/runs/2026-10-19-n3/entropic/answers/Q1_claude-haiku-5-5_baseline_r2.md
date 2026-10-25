## Short answer

The two `llama_tokenize` calls in `LlamaCppTokenizer::tokenize` are a size-query followed by a fill, not retry logic. The first call sends a null buffer and gets back the negated token count it needs. The second call is unconditional and does the real work. Nothing retries on failure.

The failure path is weak. On error, `tokenize` returns an empty vector, and the callers mostly don't check for it. One caller turns it into a silent `0`.

## The two calls

`src/inference/llama_cpp_tokenizer.cpp`:

- **Line 55:** `llama_tokenize(vocab, text, …, nullptr, 0, …)`. The buffer is null and the length is 0, so llama.cpp can only report how many tokens the text needs. The return is negative, and line 58 flips it to a positive count.
- **Line 60:** allocates the vector with that size.
- **Line 61:** `llama_tokenize(…, tokens.data(), n, …)`. This call always runs and does the actual encoding.
- **Lines 64–67:** if the fill call returns negative, it logs an error and returns `{}`.

Retry would mean a loop or a conditional second attempt after a failure. This code has neither. The comment at line 45 calls it a "sized retry," which is a misnomer.

The file does contain a real conditional retry, in `detokenize`. Lines 93 and 99 call `llama_token_to_piece` with a fixed 256-byte buffer, and only if that returns negative do they retry with the exact size. That is retry logic, and it lives in the other function.

A third copy of the size-then-fill pattern is in `tests/model/test_gh87_common_chat_e2e.cpp:49–62`. It maps a failed fill to an empty vector without logging.

## What the caller receives on failure

- `LlamaCppTokenizer::tokenize` returns `{}` when `vocab_` is null (line 52) or when the fill call fails (line 67).
- `LlamaCppBackend::tokenize` (`llama_cpp_backend.cpp:795`) also returns `{}` when no tokenizer is wired.
- The interface contract in `include/entropic/inference/tokenizer.h` says the result is "empty on failure or empty input." The two cases can't be told apart. `tests/unit/inference/tokenizer_seam_test.cpp:198` pins the empty return on the failure path.

## What the callers do with the empty vector

| Caller (`llama_cpp_backend.cpp`) | Behaviour on empty input |
|---|---|
| `do_count_tokens` (825–827) → `count_tokens` (`backend.cpp:496`) → C API `entropic_inference_count_tokens` (`inference_c_api.cpp:558`) | Returns `0`. The count-tokens path has no error channel, so a failed tokenization shows up as a plausible-looking count of zero. |
| `generate` (2561), `generate` cancellable (2643), `stream` (2728) | Logs "0 input tokens" and carries on. `run_prefill` (1484–1502) has a loop that never runs for zero tokens and then returns `true` (line 1501). Decoding and sampling then proceed with no prompt in the context. I did not trace what llama.cpp does with logits in that state. |
| `complete` (3947) | Same as above, with no guard. |
| Speculative (3593) and MTP (3921) | Have a guard: `tokens.size() < 2` returns `GENERATE_FAILED` with "prompt must have at least 2 tokens." The real cause, a tokenizer failure, gets reported as a prompt-length problem. |
| Batch (1911) | No guard. `batch_shared_prefix_len` returns 0 when any sequence is empty (`batch_util.h:52`), so the batch may still pass `batch_is_viable`. I did not trace this further. |
| `compute_prefix_token_count` (2066) | Returns `0`, which is passed on as the prefix length (line 2289). I did not trace what the prompt cache does with a zero-length prefix. |

## Bottom line

The `generate`, `stream` and `complete` paths don't check for an empty prompt, so a tokenizer failure there ends in decoding with no prompt, not in a clean error. The one check that exists, in speculative and MTP, reports the wrong cause. `count_tokens` silently returns 0. The fix would be for `tokenize` to report failure separately from empty input, for example by returning an error code or throwing, and for the generation entry points to check for it before prefill.

A hook suggested a `dossier` tool for these lookups. I don't have that tool and didn't need it.