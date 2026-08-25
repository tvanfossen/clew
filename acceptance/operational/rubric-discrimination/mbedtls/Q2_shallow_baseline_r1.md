# MBEDTLS_PRIVATE

`MBEDTLS_PRIVATE` is defined in `include/mbedtls/private_access.h`. It is a macro wrapper applied
to struct members throughout the library.

The purpose is encapsulation: mbedtls uses it to mark struct fields as private so that consumers
of the public headers know not to touch them. It is applied very widely — you see it on almost
every struct in the public headers, on fields like the ones in `mbedtls_pk_context` and the RSA
and EC key structures.

It signals intent to API consumers: members wrapped in `MBEDTLS_PRIVATE` are implementation
detail and may change between releases, so application code should use the accessor functions
instead of reaching into the struct.
