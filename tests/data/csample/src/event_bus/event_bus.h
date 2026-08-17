#ifndef EVENT_BUS_H
#define EVENT_BUS_H

#include <stdint.h>

typedef enum {
    EVENT_NONE = 0,
    EVENT_CLOUD_CMD,
} event_id_t;

typedef struct {
    event_id_t id;
    int32_t arg;
    const char *payload; /* command text for EVENT_CLOUD_CMD */
} event_t;

typedef void (*event_handler_t)(const event_t *evt);

void event_bus_init(void);
void event_bus_subscribe_cmd(event_handler_t handler);
void event_bus_publish(const event_t *evt);
int event_bus_dispatch(void);

#endif /* EVENT_BUS_H */
