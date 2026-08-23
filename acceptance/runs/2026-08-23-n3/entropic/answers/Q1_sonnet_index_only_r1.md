## Why the two calls, and is it retry logic

The index can directly show one place this pattern lives — a small `tokenize()` helper in `tests/model/test_gh87_common_chat_e2e.cpp:49-61` that talks to llama.cpp's C API by hand:

```cpp
int n = -llama_tokenize(vocab, text.c_str(), text.size(),
                        nullptr, 0, /*add_special=*/true, /*parse_special=*/true);
std::vector<llama_token> out(n);
int written = llama_tokenize(vocab, text.c_str(), text.size(),
                             out.data(), n, true, true);
out.resize(written < 0 ? 0 : written);
```

This is `llama_tokenize`'s documented calling convention, not a retry: the first call is passed a null/zero-length buffer *on purpose*, and its "failure" (a negative return) is the API's normal way of reporting the required buffer size. The second call is guaranteed to run every time, with a buffer sized from what the first call reported — it isn't conditional on the first call having gone wrong, and it isn't the same call repeated hoping for a different outcome. That's a size-probe-then-fill idiom (the same shape as `snprintf(nullptr, 0, ...)`), not retry logic. `llama_token_to_piece` (used for detokenize) follows the identical two-call contract in llama.cpp, so the same shape almost certainly appears again wherever the production detokenize path forwards to it — but I want to flag a gap rather than assert it: the production implementation, `src/inference/llama_cpp_tokenizer.cpp`, is indexed with only **one** symbol (the `LlamaCppTokenizer` constructor). The `tokenize()`/`detokenize()` bodies that the file-doc says "forward to `llama_tokenize` / `llama_token_to_piece`" aren't captured as separate indexed function bodies — only their header declarations are. So "two different places" = the test helper (confirmed) + the production seam implementation (declared/documented, but its body isn't retrievable from the index — I'd need to read the .cpp source directly to confirm the exact two-call shape there).

## The failure path: what value comes back, and what callers do with it

Tracing outward from `LlamaCppBackend::tokenize` (`src/inference/llama_cpp_backend.cpp:788-800`):

```cpp
if (!tokenizer_) { return {}; }
auto ids = tokenizer_->tokenize(text, add_special);
return {ids.begin(), ids.end()};
```

Failure — no tokenizer wired (model not loaded/ACTIVE) — collapses to an **empty vector**. There is no distinct error sentinel; empty-because-failed and empty-because-the-input-was-actually-empty are the same value. That ambiguity then propagates differently depending on the caller:

- **`do_count_tokens`** (`llama_cpp_backend.cpp:825-828`) and **`compute_prefix_token_count`** (`:2051-2068`) just take `.size()` of the result. An empty vector silently becomes token count `0` — indistinguishable from "there was nothing to tokenize."
- **`tokenize_text`** (`:837-841`) forwards the empty vector unchanged to its caller, `entropic_inference_count_tokens` (`src/inference/inference_c_api.cpp:548-562`), the public C API boundary. That function has an explicit `catch (...)` fallback (`text_len/4` estimate) for a *thrown* exception, but the tokenizer-not-wired case doesn't throw — it just returns 0 through `count_tokens()`. So a plugin caller asking "how many tokens is this?" against a backend that isn't ACTIVE gets back `0`, with no signal that the count is meaningless rather than accurate.
- **`generate_speculative_with_draft`** (`:3571-3607`) and **`generate_mtp`** (`:3906-3931`) are the exceptions: both explicitly guard `if (tokens.size() < 2)` and turn that into an actual error result (`ENTROPIC_ERROR_GENERATE_FAILED`, with a message like `"speculative prompt must have at least 2 tokens"`). These are the only two call sites where an empty/degenerate tokenize result is converted into a real, surfaced error rather than silently treated as zero.
- **`do_generate_text_only`** (`:2555-2598`) doesn't check size at all — it logs `tokens.size()` and hands the (possibly empty) vector straight to `run_prefill_cached` → `run_prefill`/`prefill_dispatch`. Whether an empty token vector there fails loudly or silently decodes zero tokens and produces an empty completion isn't something I can confirm from the index — `run_prefill`'s body wasn't pulled in this pass, and this is exactly the kind of behavior that needs reading the decode loop, not just the call graph.

So the pattern across the codebase is inconsistent: two generation paths (speculative, MTP) treat a too-short/empty tokenization as a hard error; the token-counting paths and the plain-text generation path do not distinguish it from legitimate emptiness at all.
