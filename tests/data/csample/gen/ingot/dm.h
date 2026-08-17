#ifndef DM_H
#define DM_H

#include <stdint.h>

typedef enum {
    DM_OK = 0,
    DM_ERR_UNKNOWN_KEY,
} DM_RETURN_CODE;

typedef uint32_t dm_key_t;

typedef union {
    uint8_t u8;
    int16_t i16;
    uint32_t u32;
} dm_val_t;

typedef void (*dm_change_cb_t)(dm_key_t key);

DM_RETURN_CODE DataModel_SetIntegralTypeByKey(dm_key_t key, const dm_val_t *value);
dm_val_t DataModel_GetIntegralTypeByKey(dm_key_t key);
void DataModel_Initialize(dm_change_cb_t cb);

#endif /* DM_H */
