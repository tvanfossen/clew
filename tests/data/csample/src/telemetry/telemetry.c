/** @participant Telemetry */

#include "telemetry.h"

#include <stdio.h>

#include "../../gen/ingot/dm_helpers.h"

static int s_reports_sent;

/**
 * @brief Reset telemetry counters.
 * @version 1.0
 * @req REQ-0400
 */
void telemetry_init(void)
{
    s_reports_sent = 0;
}

/**
 * @brief Format current data-model values for upstream publication.
 * @version 1.0
 * @req REQ-0400
 */
void telemetry_report(void)
{
    printf("telemetry: battery=%dmV (report %d)\n",
           (int)DataModel_Get_DEMOBOT_POWER_BATTERY_MV(), ++s_reports_sent);
}
