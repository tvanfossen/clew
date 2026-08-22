# Tokenizer retry logic

The double call lives in `src/inference/llama_cpp_tokenizer.cpp`, in both `tokenize` (line 49)
and `detokenize` (line 86).

In `tokenize`, the code calls `llama_tokenize` once, and if the result comes back negative it
calls it again with a properly sized buffer. In `detokenize` the same shape appears: it calls
`llama_token_to_piece` into a 256-byte stack buffer, and if that returns a negative value it
retries into a heap-allocated `std::vector<char>`.

This is defensive retry logic around a C API that can fail transiently. If the second call also
fails, `tokenize` logs an error through the logger and `detokenize` falls back to returning an
empty string, so a failure degrades gracefully rather than propagating an exception.

Yes, I would describe this as retry logic — it is a standard retry-on-failure pattern applied to
a foreign function boundary, and it makes the tokenizer resilient to intermittent errors from
llama.cpp.
