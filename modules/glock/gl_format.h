/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef GL_FORMAT_H
#define GL_FORMAT_H
#include <stddef.h>
#include <stdarg.h>
/* Deliberately small, bounded C99 formatter for our 32-bit integer/string
 * formats. EOS M's ROM vsnprintf does not implement unsigned decimal. */
int gl_vsnprintf(char *out, size_t capacity, const char *format, va_list args);
int gl_snprintf(char *out, size_t capacity, const char *format, ...);
#endif
