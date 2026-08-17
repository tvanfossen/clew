/** @participant Sensor Driver */

#include "sensor_driver.h"

#include <stdint.h>

#include "../../gen/ingot/dm_helpers.h"

static int16_t s_last_sample;

/**
 * @brief Read the battery ADC channel (simulated hardware).
 * @version 1.0
 * @utility
 * @return Battery voltage in millivolts.
 */
static int16_t hw_read_battery_adc(void)
{
    /* Simulated discharge curve for the sample. */
    s_last_sample = (int16_t)((s_last_sample > 0) ? s_last_sample - 1 : 4200);
    return s_last_sample;
}

/**
 * @brief Prime the sensor driver's sampling state.
 * @version 1.0
 * @req REQ-0100
 */
void sensor_init(void)
{
    s_last_sample = 4200;
}

/**
 * @brief Sample battery voltage and publish it into the data model.
 * @version 1.0
 * @req REQ-0100
 */
void sensor_poll(void)
{
    DataModel_Set_DEMOBOT_POWER_BATTERY_MV(hw_read_battery_adc());
}
