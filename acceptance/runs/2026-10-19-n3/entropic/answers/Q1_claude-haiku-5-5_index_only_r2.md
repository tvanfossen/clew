**Why it calls twice, and whether that's retry logic**

The index confirms one doubled call, in `LlamaCppTokenizer::tokenize` (`src/inference/llama_cpp_tokenizer.h:44`). Its doc says it returns empty "if `llama_tokenize` returned a negative actual-count on the sized retry." That is llama.cpp's size-probe protocol: the first call passes a buffer, gets back a negative number meaning "I need this many slots," and the second call fills a buffer of that size. I would not call it retry logic. Nothing failed in a way the code is recovering from; the first call is how the caller learns the required size.

The second doubled call is in `detokenize` (`llama_cpp_tokenizer.h:47`), which per its doc has a "retry decode" step. I'd treat it the same way, as a size-or-buffer protocol rather than recovery from a transient error.

Caveat: `dossier` won't return the body of `LlamaCppTokenizer::tokenize` or `detokenize` (the .cpp files aren't indexed as symbols), so the mechanics above come from the doxygen text, not the code. I also couldn't confirm the two calls happen in one flow. The doc only establishes that the retry is conditional on a negative first return.

**What the caller gets on failure**

Failure is signalled by an empty value, not an error code or exception:

- `LlamaCppTokenizer::tokenize` returns an empty vector if `vocab_` is null or the sized retry gives a negative count.
- `LlamaCppBackend::tokenize` (`llama_cpp_backend.cpp:788`) returns `{}` when `tokenizer_` is unset, and otherwise copies the adapter's result through.
- `Tokenizer::count_tokens` (`tokenizer.h:74`) returns `tokenize(text, false).size()`, so failure becomes `0`.
- `LlamaCppBackend::do_count_tokens` (`llama_cpp_backend.cpp:825`) returns that same `0`.
- `detokenize` returns an empty string on failure.
- `tokenize_text` is documented as "empty if COLD or error."

So a token count of `0` cannot be told apart from "the text tokenized to nothing" or "the vocab was null."

**What the callers do with it**

- `do_complete` (`llama_cpp_backend.cpp:3941`) tokenizes the prompt, logs `"{} input tokens"` with the empty count, and passes the empty vector straight into `decode_loop`. It has no empty check, so an empty prompt goes into decode. I did not read `decode_loop`, so I can't say what it does with zero tokens.
- `compute_prefix_token_count` (`llama_cpp_backend.h:2051`) returns `0` for a failed system-prompt tokenization. Its caller `prefill_dispatch` then uses `0` as the prefix length for cache handling. I didn't read `prefill_and_cache_prefix`, so I don't know what a zero-length prefix does to the cache.
- `do_count_tokens` has no callers in the index other than the interface, so a silent `0` goes to whatever calls `count_tokens` externally.

The pattern is that tokenization failure is silent: the caller gets an empty result and no error is raised or logged at the failure point. If you want this hardened, the first step is to have `LlamaCppTokenizer::tokenize` log at WARNING/ERROR with the llama.cpp return code (per the repo's observability rules), and to make the empty-prompt case in `do_complete` an explicit error.