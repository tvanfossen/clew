#ifndef INTEGER_STORAGE_H
#define INTEGER_STORAGE_H

#include <stdint.h>

#include "dm.h"

DM_RETURN_CODE IntegerStorage_SetUINT8Key(dm_key_t key, uint8_t value);
DM_RETURN_CODE IntegerStorage_GetUINT8Key(dm_key_t key, uint8_t *out);

#endif /* INTEGER_STORAGE_H */
