/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef FX_PREVIEW_H
#define FX_PREVIEW_H
/* Native UYVY LCD layouts in the eligible DryOS ports: 720x480, or 720x240
 * on 1100D. In particular, do not mistake 540-wide RCA for a supported LCD.
 * Reject external layouts and unknown strides before touching pixels. */
static inline int fx_preview_geometry(int width,int height,int pitch)
{
    return width==720&&(height==480||height==240)&&pitch==1440;
}
#endif
