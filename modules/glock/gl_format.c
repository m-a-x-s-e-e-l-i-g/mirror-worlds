/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "gl_format.h"
#include <stdint.h>
#include <limits.h>

struct buffer { char *out; size_t capacity, count; };
static void put(struct buffer *b, char c)
{
    if (b->capacity && b->count < b->capacity - 1) b->out[b->count] = c;
    b->count++;
}
int gl_vsnprintf(char *out, size_t capacity, const char *format, va_list args)
{
    struct buffer b = {out, capacity, 0};
    int valid = 1;
    if (!format || (!out && capacity)) return -1;
    while (*format) {
        if (*format++ != '%') { put(&b, format[-1]); continue; }
        unsigned width = 0;
        char pad = *format == '0' ? '0' : ' ';
        while (*format >= '0' && *format <= '9') {
            width = width * 10 + (unsigned)(*format++ - '0');
            if (width > 64) { valid = 0; break; }
        }
        if (!valid || !*format) { valid = 0; break; }
        char spec = *format++;
        if (spec == '%') { put(&b, '%'); continue; }
        if (spec == 's') {
            const char *s = va_arg(args, const char *);
            if (!s) s = "(null)";
            size_t n = 0; while (s[n]) n++;
            while (width > n) { put(&b, ' '); width--; }
            while (*s) put(&b, *s++);
        } else if (spec == 'd' || spec == 'u' || spec == 'x') {
            uint32_t value;
            int negative = 0;
            if (spec == 'd') {
                int v = va_arg(args, int); negative = v < 0;
                value = negative ? 0u - (uint32_t)v : (uint32_t)v;
            } else value = va_arg(args, unsigned int);
            char digits[10]; unsigned n = 0, base = spec == 'x' ? 16 : 10;
            do { digits[n++] = "0123456789abcdef"[value % base]; value /= base; } while (value);
            if (negative && pad == '0') put(&b, '-');
            while (width > n + (unsigned)negative) { put(&b, pad); width--; }
            if (negative && pad != '0') put(&b, '-');
            while (n) put(&b, digits[--n]);
        } else { valid = 0; break; }
    }
    if (capacity) out[b.count < capacity ? b.count : capacity - 1] = 0;
    return valid && b.count <= INT_MAX ? (int)b.count : -1;
}
int gl_snprintf(char *out, size_t capacity, const char *format, ...)
{
    va_list args; va_start(args, format);
    int result = gl_vsnprintf(out, capacity, format, args);
    va_end(args); return result;
}
