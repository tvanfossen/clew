# Why the tokenizer calls twice — and why it is not retry logic

Both sites are in `src/inference/llama_cpp_tokenizer.cpp`: `tokenize` at `:49` and `detokenize`
at `:86`.

## It is a size-negotiation protocol

llama.cpp's API reports a buffer that is too small by returning the **required size as a negative
number**. Both functions exploit that:

- `tokenize` makes the first call with `nullptr` and `0` purely to *ask the size* — it never
  intends to write. Line 58 is `if (n < 0) { n = -n; }`, converting the reported deficit into a
  length, and the second call passes a vector of exactly that size.
- `detokenize` tries a fixed 256-byte **stack** buffer first (`char buf[256];` at `:92`). If that
  succeeds it returns immediately. Only on a negative return does it heap-allocate, and the
  comment at `:97` says so outright: *"Buffer too small — retry with exact size. n holds
  -required_size."* The vector at `:98` is sized `-n`.

So the two sites differ: `tokenize` always negotiates before writing, while `detokenize` has a
fast path for the common case and negotiates only when the token does not fit.

## So, no — I would not call it retry logic

There is no backoff, no delay, no attempt counter and no loop. There is **exactly one** second
call, and it cannot fail for the same reason the first did, because the buffer is now precisely
the size the API asked for. Calling this a retry imports an error-recovery model the code does not
have: nothing here is guarding against a transient fault.

## The second call is terminal

If the second call comes back bad, neither function tries again:

- `tokenize` logs `"Tokenization failed for text of length {}"` and returns an empty vector
  (`:64-68`).
- `detokenize`'s closing ternary returns an empty string when `n` is not positive.

That is the honest signature of size negotiation rather than resilience — a genuine retry loop
would escalate or repeat, and this one gives up immediately, because a second failure means
something other than a small buffer.
