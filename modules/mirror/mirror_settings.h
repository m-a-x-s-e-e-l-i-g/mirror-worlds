/* SPDX-License-Identifier: GPL-2.0-or-later; Max Seelig (MAXmade). */
#ifndef MIRROR_SETTINGS_H
#define MIRROR_SETTINGS_H
#include "fx_mirror_edges.h"
#define mirror_settings_load FX(settings_load)
#define mirror_settings_save FX(settings_save)
typedef struct {unsigned enabled,placement,width,height;} mirror_settings;
static inline unsigned mirror_edge_mask(unsigned placement)
{static const unsigned masks[]={1,2,4,8,3,12,15};return placement<7?masks[placement]:0;}
static inline fx_params mirror_settings_params(const mirror_settings*s)
{fx_params p={{FX_MIRROR_EDGES,mirror_edge_mask(s->placement),s->width+2,s->height+2}};return p;}
static inline int mirror_settings_valid(const mirror_settings*s)
{fx_params p=mirror_settings_params(s);return s->enabled<=1&&s->placement<7&&s->width<5&&s->height<5&&fx_edges_valid(&p);}
/* Two alternating checked preference slots, independent of diagnostic logging
 * and ML's global autosave option. Only called from idle worker/init tasks. */
int mirror_settings_load(mirror_settings*out);
int mirror_settings_save(const mirror_settings*settings);
#endif
