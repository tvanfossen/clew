/** @participant Data Model */

#include "dm.h"

#include <pthread.h>
#include <stdint.h>

#include "dm_key.h"
#include "integer_storage.h"

static pthread_mutex_t dm_mutex = PTHREAD_MUTEX_INITIALIZER;
static dm_change_cb_t s_change_cb;

/**
 * @brief Store a keyed integral value and fire the change callback.
 * @version 1.0
 * @param key Data-model key the value belongs to.
 * @param value Value to store.
 * @return DM_OK on success, DM_ERR_UNKNOWN_KEY otherwise.
 */
DM_RETURN_CODE DataModel_SetIntegralTypeByKey(dm_key_t key, const dm_val_t *value)
{
    DM_RETURN_CODE rc;

    pthread_mutex_lock(&dm_mutex);
    rc = IntegerStorage_SetUINT8Key(key, value->u8);
    pthread_mutex_unlock(&dm_mutex);

    if (rc == DM_OK && s_change_cb != 0) {
        s_change_cb(key);
    }
    return rc;
}

/**
 * @brief Read a keyed integral value out of the store.
 * @version 1.0
 * @param key Data-model key to read.
 * @return The stored value, or a zeroed value for an unknown key.
 */
dm_val_t DataModel_GetIntegralTypeByKey(dm_key_t key)
{
    dm_val_t out;

    pthread_mutex_lock(&dm_mutex);
    IntegerStorage_GetUINT8Key(key, &out.u8);
    pthread_mutex_unlock(&dm_mutex);

    return out;
}

/**
 * @brief Register the change callback fired on every successful set.
 * @version 1.0
 * @param cb Callback invoked with the changed key.
 */
void DataModel_Initialize(dm_change_cb_t cb)
{
    s_change_cb = cb;
}
