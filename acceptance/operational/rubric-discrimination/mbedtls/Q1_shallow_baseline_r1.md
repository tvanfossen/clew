# Concurrency in mbedtls

mbedtls has thread support and mutex handling. The relevant configuration macros are
`MBEDTLS_THREADING_C` and `MBEDTLS_THREADING_PTHREAD`, declared in
`include/mbedtls/mbedtls_config.h`.

The clearest example of concurrency is `programs/ssl/ssl_pthread_server.c`, which spawns a
thread per incoming connection. At line 277 it calls `pthread_create` with
`handle_ssl_connection` as the entry function, so each accepted connection runs the full TLS
handshake and record processing on its own thread.

There is also a `debug_mutex` declared at line 65 of the same file, which is used around debug
printing so that output from different connections does not get mixed together.

`library/threading.c` provides the mutex abstraction layer that the rest of the library uses
when threading is enabled — `mbedtls_mutex_lock`, `mbedtls_mutex_unlock` and friends wrap the
platform primitives.

So: mbedtls runs one thread per TLS connection in the pthread server, and `debug_mutex`
protects the shared debug output stream.
