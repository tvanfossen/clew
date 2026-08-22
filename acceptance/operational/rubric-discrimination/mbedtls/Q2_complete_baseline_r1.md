# What MBEDTLS_PRIVATE actually does

The whole definition is three lines in `include/mbedtls/private_access.h`:

```c
#ifndef MBEDTLS_ALLOW_PRIVATE_ACCESS
#define MBEDTLS_PRIVATE(member) private_##member
#else
#define MBEDTLS_PRIVATE(member) member
#endif
```

## The direction of the default matters

**By default the macro RENAMES the member** — `MBEDTLS_PRIVATE(foo)` becomes `private_foo`.
Defining `MBEDTLS_ALLOW_PRIVATE_ACCESS` before including the header makes it expand to `foo`,
unchanged. The opt-in is what turns the renaming *off*, not on.

## Two consumers, one header

Which expansion you get is decided entirely by whether you defined the opt-in. Library-internal
code and tests define `MBEDTLS_ALLOW_PRIVATE_ACCESS` and therefore see plain member names; an
ordinary consumer of the public headers does not, and sees the renamed ones. One macro serves
both audiences out of the same header.

## It breaks the name, not the layout

This enforces API opacity at **compile time by breaking the member name**, not by hiding the
struct. The struct remains fully defined in the public header, so its layout and size are
unchanged and it can still be stack-allocated and `sizeof`'d — which is why mbedtls can do this
without moving to opaque pointers. What breaks is source code that names a member directly:
`ctx.foo` fails to compile, `ctx.private_foo` works but is visibly reaching past the API.

## Scale

It is applied at the scale of many hundreds of sites — roughly 875 occurrences across about 66
files. The distribution is heavily skewed toward the public headers: the large majority of those
files are under `include/`, with a handful under `library/` and a couple under `programs/`. That
skew is the point — the macro exists for the headers a consumer compiles against.
