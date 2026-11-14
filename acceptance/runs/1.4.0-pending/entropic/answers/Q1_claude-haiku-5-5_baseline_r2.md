**Short answer:** the two calls are not in two places. They are adjacent lines in one function, `LlamaCppTokenizer::tokenize` (`src/inference/llama_cpp_tokenizer.cpp:55` and `:61`). The first call is a size probe, not a retry, and the second call runs unconditionally on every tokenization.

## Why it calls twice

llama.cpp's `llama_tokenize` has no "allocate for me" mode. The idiom is:

1. Call with a null buffer and capacity 0. It returns the negative of the required token count.
2. Negate it, allocate a `std::vector<int32_t>` of that size, and call again to fill it.

The code follows that exactly. The docstring at line 45 calls the second step a "sized retry," which is misleading. Nothing failed before the second call, and it is never gated on the first call's result. The cost is that every tokenization runs the tokenizer twice. A generous fixed buffer, or resizing only when the first call reports a short buffer, would avoid that.

## What the caller receives on failure

If the second call returns a negative value, the function logs at error level (length only, not the text) and returns `{}`. There is no error code, exception, or status. A missing vocab (`vocab_ == nullptr`) also returns `{}`, silently.

The empty vector is ambiguous. An empty prompt with `add_special=false` also produces `{}`, so no caller can tell "failed" from "nothing to tokenize."

## What the callers do with it

- **`LlamaCppBackend::tokenize`** (`llama_cpp_backend.cpp:788`) passes the empty vector through.
- **Token counting** is the most silent path. `do_count_tokens` returns 0 (`:825`), which `InferenceBackend::count_tokens` passes on (`backend.cpp:496`), and `entropic_inference_count_tokens` returns to plugins (`inference_c_api.cpp:548`). A failed count looks like "zero tokens," so a plugin doing budget math sees plenty of room. The C API docstring says "estimate on error," but the `text_len/4` fallback only runs on an exception, not on this tokenizer failure.
- **Speculative and MTP generation** (`llama_cpp_backend.cpp:3594`, `:3922`) check `tokens.size() < 2` and return `GENERATE_FAILED` with "prompt must have at least 2 tokens." The real cause is a tokenization failure, so the message is wrong.
- **Plain generate, cancellable generate, and stream** (`:2561`, `:2643`, `:2728`), **`do_complete`** (`:3947`), and **batch generate** (`:1911`) have no empty check. Generation proceeds with zero input tokens. `decode_tokens_from` returns `true` immediately when there is nothing to decode (`:1960`), so no error is raised and sampling starts with nothing decoded. I did not trace what the sampler reads in that state. That is the next thing to verify, and it is the most likely way a tokenizer failure becomes a hard-to-diagnose bad generation.
- **System-prefix count** (`:2066`) returns 0, and the prefill logic treats `prefix_tokens <= 0` as "no cache," so that case is benign.

## Suggested fixes

- Return a status alongside the vector, or throw inside the seam and catch at the C boundary, so the empty result is distinguishable from an empty prompt.
- Have generation entry points reject empty token vectors with a tokenization-specific error.
- Make `count_tokens` surface failure rather than 0, and correct the C API docstring.

Caveat: I did not inspect `mtmd_tokenize` (`llama_cpp_backend.cpp:2407`), the multimodal tokenizer. If "two different places" referred to that, the analysis above doesn't cover it.