/** @participant Command Handler */

#include "command_handler.h"

#include <stdio.h>
#include <string.h>

#include "../event_bus/event_bus.h"
#include "../telemetry/telemetry.h"

static void handle_cloud_command(const event_t *evt);

/**
 * @brief Subscribe the cloud command handler to the event bus.
 * @version 1.0
 * @req REQ-0300
 */
void command_handler_init(void)
{
    event_bus_subscribe_cmd(handle_cloud_command);
}

/**
 * @brief Route a cloud command payload to its feature handler.
 * @version 1.0
 * @req REQ-0300
 * @receives MQTT:cmd/req
 * @param evt Cloud command event; payload holds the command text.
 */
static void handle_cloud_command(const event_t *evt)
{
    if (evt->payload == 0) {
        return;
    }
    if (strcmp(evt->payload, "status") == 0) {
        telemetry_report();
        return;
    }
    printf("command: unknown payload '%s' dropped\n", evt->payload);
}
