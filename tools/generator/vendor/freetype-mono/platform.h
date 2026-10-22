/* Minimal C library boundary for FreeType's standalone scanner. */
#ifndef FONT_MONO_PLATFORM_H
#define FONT_MONO_PLATFORM_H
#include <stddef.h>
#include <stdint.h>
#if defined(__wasm__)
/* Rust's compiler-builtins supplies memset; no WASI/libc is required. */
void *memset(void *dest, int value, size_t count);
#else
#include <string.h>
#endif
#endif
