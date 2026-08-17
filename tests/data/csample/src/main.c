/** @participant App */

#include "command/command_handler.h"
#include "dispatch/dm_event_dispatch.h"
#include "event_bus/event_bus.h"
#include "sensor/sensor_driver.h"
#include "telemetry/telemetry.h"

#define DEMO_LOOP_PASSES 3

/**
 * @brief Run a bounded main loop: poll, dispatch, report.
 * @version 1.0
 * @req REQ-0200
 */
static void app_run(void)
{
    event_t demo_cmd;
    int pass;

    demo_cmd.id = EVENT_CLOUD_CMD;
    demo_cmd.arg = 0;
    demo_cmd.payload = "status";
    event_bus_publish(&demo_cmd);

    for (pass = 0; pass < DEMO_LOOP_PASSES; pass++) {
        sensor_poll();
        event_bus_dispatch();
    }
}

/**
 * @brief Initialise every subsystem, then enter the main loop.
 * @version 1.0
 * @req REQ-0200
 * @return Process exit code (always 0 in the sample).
 */
int main(void)
{
    event_bus_init();
    dm_event_dispatch_init();
    sensor_init();
    telemetry_init();
    command_handler_init();
    app_run();
    return 0;
}
