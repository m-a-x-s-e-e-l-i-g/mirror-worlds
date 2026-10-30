/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Read model data from the pinned QEMU-EOS source, without camera ROMs.
 * Default inheritance follows hw/eos/eos.c:get_model_from_name. */
#include <stdio.h>
#include <stddef.h>
#include "model_list.h"

int main(void)
{
    const struct eos_model_desc *defaults = NULL;
    unsigned count = 0;
    puts("[");
    for (const struct eos_model_desc *entry = eos_model_list; entry->digic_version; entry++) {
        if (!entry->name) { defaults = entry; continue; }
        if (!defaults) return 1;
        struct eos_model_desc model = *entry;
        for (unsigned i = 0; i < sizeof(model.params)/sizeof(model.params[0]); i++)
            if (!model.params[i]) model.params[i] = defaults->params[i];
        printf("%s{\"model\":\"%s\",\"digic\":%u,\"rom0_bytes\":%u,"
               "\"rom1_bytes\":%u,\"serial_flash_bytes\":%u,\"cache_alias_bit\":%u}",
               count++ ? ",\n" : "", model.name, model.digic_version,
               model.rom0_size, model.rom1_size, model.serial_flash_size, model.caching_bit);
    }
    puts("\n]");
    return 0;
}
