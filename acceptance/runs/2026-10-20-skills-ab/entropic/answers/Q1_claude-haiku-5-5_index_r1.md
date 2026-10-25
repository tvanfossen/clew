**Why it calls twice:** `LlamaCppTokenizer::tokenize` (`src/inference/llama_cpp_tokenizer.cpp:49-71`) uses llama.cpp's size-probe pattern. The first `llama_tokenize` call passes a null buffer and zero capacity. llama.cpp answers with the negative of the required token count, which the code negates to get `n`. The second call allocates `n` slots and does the real encoding. The first call does no useful work; it only asks how big the output needs to be.

The same pattern appears in `detokenize` (`llama_cpp_tokenizer.cpp:86-105`) with `llama_token_to_piece`. There the second call is conditional. It runs only when the 256-byte stack buffer is too small.

**Is it retry logic?** No. Nothing failed in the first call, and nothing is repeated on failure. The first call is a size query and the second is the actual operation. The header comment at `llama_cpp_tokenizer.h` says "sized retry", which is the source of the confusion. "Probe, then allocate and fill" is the accurate description. The only path that resembles a retry is the detokenize buffer resize, and that is still a resize, not a retry.

**What the caller receives on failure:** The tokenizer returns an empty `std::vector<int32_t>` and logs one error line with only the text length. That is the only signal. The call chain is:

| Caller | What it does with the empty result |
|---|---|
| `LlamaCppBackend::tokenize` (`llama_cpp_backend.cpp:788`) | Forwards the empty vector. It also returns `{}` when no tokenizer is wired, so "no tokenizer" and "tokenization failed" look identical. |
| `do_count_tokens` (`:825`) | Returns `0`. The C API `entropic_inference_count_tokens` passes that `0` straight through, so a failure looks like empty input. |
| `compute_prefix_token_count` (`:2051`) | Returns `0`, which the prefill dispatcher reads as "no system prefix". |
| `do_generate_text_only` (`:2555`), `do_complete` (`:3941`), and the streaming and batch paths | Use the vector without a visible emptiness check and pass it to `run_prefill_cached` or `decode_loop`. I did not trace those downstream functions, so whether a zero-token prompt is rejected there is unverified. |
| Speculative (`:3593`) and MTP (`:3921`) | Reject `tokens.size() < 2` with `GENERATE_FAILED` and the message "must have at least 2 tokens". This is the only check that surfaces a failure, and it reports the wrong cause. |

**Other things I noticed:**
- The error log omits the text content and the model, which conflicts with the global rule to log errors with full context.
- The failure branch is effectively reachable only if the second call disagrees with the first, which should not happen with a fixed vocab. The more likely failure is an empty or zero-token result, and that path is handled by the callers in the table above, not by the tokenizer.