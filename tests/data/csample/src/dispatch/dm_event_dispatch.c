/** @participant DM Dispatch */

#include "dm_event_dispatch.h"

#include <stdint.h>

#include "../../gen/ingot/dm_helpers.h"
#include "../sound/sound_service.h"

/**
 * @brief React to data-model key changes reported by the generated store.
 * @version 1.0
 * @req REQ-0500
 * @param key_id Changed key (DM_KEY_* from generated key_definitions.h).
 */
static void handle_dm_key_event(uint32_t key_id)
{
    switch (key_id) {
    case DM_KEY_DEMOBOT_UX_SOUND_EVENT:
        sound_play_findme(DataModel_Get_DEMOBOT_UX_SOUND_EVENT());
        break;
    case DM_KEY_DEMOBOT_POWER_BATTERY_MV:
        break; /* battery updates are polled by telemetry, not event-driven */
    default:
        break;
    }
}

/**
 * @brief Initialise the generated data model with our change handler.
 * @version 1.0
 * @req REQ-0500
 */
void dm_event_dispatch_init(void)
{
    DataModel_Initialize(handle_dm_key_event);
}
