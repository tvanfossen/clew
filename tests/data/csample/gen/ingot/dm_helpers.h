#ifndef DM_HELPERS_H
#define DM_HELPERS_H

#include <stdint.h>

#include "dm.h"
#include "dm_key.h"

/* Per-key inline accessors, in the shape a code generator emits them: the key is
 * part of the function NAME, so a setter takes exactly the value and a getter
 * takes nothing. That arity is what the shared-key detector gates on. */

static inline uint32_t DataModel_Get_DEMOBOT_UX_SOUND_EVENT(void)
{
    dm_val_t v = DataModel_GetIntegralTypeByKey(DM_KEY_DEMOBOT_UX_SOUND_EVENT);
    return v.u32;
}

/* The `...ByKey` dispatcher underneath takes the key as an ARGUMENT, which is
 * why `DataModel_Set_` and `DataModel_Set` are two DIFFERENT accessor families
 * with two different arities. Collapsing them to the common `DataModel_Set`
 * merges a real per-key family with a dispatcher fragment, and the merged arity
 * then rejects both.
 */
static inline DM_RETURN_CODE DataModel_Set_DEMOBOT_POWER_BATTERY_MV(int16_t x)
{
    dm_val_t v;
    v.i16 = x;
    return DataModel_SetIntegralTypeByKey(DM_KEY_DEMOBOT_POWER_BATTERY_MV, &v);
}

/* Reader half of the same key. */
static inline int16_t DataModel_Get_DEMOBOT_POWER_BATTERY_MV(void)
{
    dm_val_t v = DataModel_GetIntegralTypeByKey(DM_KEY_DEMOBOT_POWER_BATTERY_MV);
    return v.i16;
}

#endif /* DM_HELPERS_H */
