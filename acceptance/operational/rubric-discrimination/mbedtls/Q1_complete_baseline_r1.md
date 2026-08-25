# What actually runs concurrently in mbedtls as shipped

**Nothing.** A default build of mbedtls creates no threads at all.

## The gate

Concurrency in this repository is gated on two configuration macros, `MBEDTLS_THREADING_C` and
`MBEDTLS_THREADING_PTHREAD`, both declared in `include/mbedtls/mbedtls_config.h`. Both ship
**commented out** — line 3787 is `//#define MBEDTLS_THREADING_C` and line 2196 is
`//#define MBEDTLS_THREADING_PTHREAD`. A default build therefore defines neither.

The consequence is visible at `programs/ssl/ssl_pthread_server.c:24`, where

```c
#elif !defined(MBEDTLS_THREADING_C) || !defined(MBEDTLS_THREADING_PTHREAD)
```

selects a stub `main()` that prints "MBEDTLS_THREADING_PTHREAD not defined." and exits. The
threaded body only begins at the `#else` on line 30.

## Where the threading lives

Both thread-creation sites are **outside `library/`** — they are example programs, not the
library:

| file | site | mechanism |
|---|---|---|
| `programs/ssl/ssl_pthread_server.c` | `:277` | `pthread_create`, entry `handle_ssl_connection` (`:98`) |
| `programs/test/benchmark.c` | `:430` | `_beginthread(TimerProc, 0, NULL)`, `TimerProc` at `:410` |

Nothing in `library/` creates a thread. `library/threading.c` supplies the mutex abstraction used
*by* threaded callers but does not itself spawn anything.

Note that the benchmark timer is a different case from the SSL server: `_beginthread` is a
Windows CRT call, so that thread is gated on a **platform** condition rather than on the
threading configuration. An answer that says "no threads because the threading macros are off"
gets the right conclusion by an incomplete argument.

## What protects what

Were threading enabled, `debug_mutex` (declared `ssl_pthread_server.c:65`, locked `:73`,
unlocked `:80`, initialised `:321`, freed `:483`) **serialises debug output** so that
concurrently-served connections do not interleave their logging into one stream.
