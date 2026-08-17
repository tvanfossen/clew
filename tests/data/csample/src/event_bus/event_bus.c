/** @participant Event Bus */

#include "event_bus.h"

#include <string.h>

#define EVENT_QUEUE_DEPTH 8

static event_t s_queue[EVENT_QUEUE_DEPTH];
static int s_head;
static int s_tail;
static event_handler_t s_cmd_handler;

/**
 * @brief Reset the event queue and clear all handler subscriptions.
 * @version 1.0
 * @req REQ-0200
 */
void event_bus_init(void)
{
    memset(s_queue, 0, sizeof(s_queue));
    s_head = 0;
    s_tail = 0;
    s_cmd_handler = 0;
}

/**
 * @brief Subscribe a handler to cloud command events.
 * @version 1.0
 * @req REQ-0200
 * @param handler Callback invoked for each EVENT_CLOUD_CMD on dispatch.
 */
void event_bus_subscribe_cmd(event_handler_t handler)
{
    s_cmd_handler = handler;
}

/**
 * @brief Enqueue an event for delivery on the next dispatch pass.
 * @version 1.0
 * @req REQ-0200
 * @param evt Event to copy into the queue; dropped if the queue is full.
 */
void event_bus_publish(const event_t *evt)
{
    int next = (s_tail + 1) % EVENT_QUEUE_DEPTH;
    if (next == s_head) {
        return; /* queue full: drop */
    }
    s_queue[s_tail] = *evt;
    s_tail = next;
}

/**
 * @brief Drain the queue, delivering each event to its subscribed handler.
 * @version 1.0
 * @req REQ-0200
 * @return Number of events delivered this pass.
 */
int event_bus_dispatch(void)
{
    int delivered = 0;
    while (s_head != s_tail) {
        const event_t *evt = &s_queue[s_head];
        s_head = (s_head + 1) % EVENT_QUEUE_DEPTH;
        switch (evt->id) {
        case EVENT_CLOUD_CMD:
            if (s_cmd_handler) {
                s_cmd_handler(evt);
            }
            break;
        default:
            break;
        }
        delivered++;
    }
    return delivered;
}
