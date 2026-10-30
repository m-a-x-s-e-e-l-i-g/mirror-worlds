#ifndef MIRROR_SETTINGS_SDK_H
#define MIRROR_SETTINGS_SDK_H
#include <fcntl.h>
#include "fx_sdk.h"
const char *get_config_dir(void);
FILE *FIO_OpenFile(const char*,unsigned);
int FIO_ReadFile(FILE*,void*,size_t);
#endif
