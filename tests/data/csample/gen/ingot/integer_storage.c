/** @participant Integer Storage */

#include "integer_storage.h"

#define STORAGE_SLOTS 2

static uint8_t s_slots[STORAGE_SLOTS];

/**
 * @brief Write one keyed byte into the backing store.
 * @version 1.0
 * @param key Slot to write.
 * @param value Byte to store.
 * @return DM_OK when the key is in range, DM_ERR_UNKNOWN_KEY otherwise.
 */
DM_RETURN_CODE IntegerStorage_SetUINT8Key(dm_key_t key, uint8_t value)
{
    if (key >= STORAGE_SLOTS) {
        return DM_ERR_UNKNOWN_KEY;
    }
    s_slots[key] = value;
    return DM_OK;
}

/**
 * @brief Read one keyed byte out of the backing store.
 * @version 1.0
 * @param key Slot to read.
 * @param out Receives the stored byte.
 * @return DM_OK when the key is in range, DM_ERR_UNKNOWN_KEY otherwise.
 */
DM_RETURN_CODE IntegerStorage_GetUINT8Key(dm_key_t key, uint8_t *out)
{
    if (key >= STORAGE_SLOTS) {
        return DM_ERR_UNKNOWN_KEY;
    }
    *out = s_slots[key];
    return DM_OK;
}
