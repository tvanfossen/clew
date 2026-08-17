# Q3 — src — haiku — run 1

## Answer

**Does mbedtls create threads?**

**Confidence: Very High**

**Short Answer:** The mbedtls *library* itself does **NOT** create threads. However, demonstration *programs* in the project do create threads.

### The Library (No Thread Creation)

The core library code contains no thread creation calls. The `library/threading.c` file (`library/threading.c:50-111`) implements only **mutex management** — providing functions for initializing, locking, and unlocking pthreads mutexes to protect shared resources. Verification: no `pthread_create`, `CreateThread`, `xTaskCreate`, or `fork()` calls exist anywhere in the `library/` directory.

### Demonstration Programs (Thread Creation)

The project includes example server programs that create threads:

**1. `programs/ssl/ssl_pthread_server.c:277`**
```c
if ((ret = pthread_create(&threads[i].thread, NULL, handle_ssl_connection,
                          &threads[i].data)) != 0) {
```

**What these threads do:**
- The worker threads execute the `handle_ssl_connection()` function (`programs/ssl/ssl_pthread_server.c:98`)
- Each thread handles a single SSL/TLS client connection:
  - Performs SSL/TLS handshake (`programs/ssl/ssl_pthread_server.c:129`)
  - Reads HTTP requests (`programs/ssl/ssl_pthread_server.c:148`)
  - Writes HTTP responses (`programs/ssl/ssl_pthread_server.c:192`)
  - Closes the connection gracefully (`programs/ssl/ssl_pthread_server.c:213`)
- Up to `MAX_NUM_THREADS` (5) worker threads can be concurrently active (`programs/ssl/ssl_pthread_server.c:63`)

**2. `programs/ssl/ssl_fork_server.c`**
- Also provides a demonstration server using `fork()` for process-based concurrency instead of pthreads

## Gaps

None identified. The codebase is straightforward on this point: the library provides thread-safety mechanisms (mutexes) but does not spawn threads; only the demonstration programs do.
