/** @participant Legacy */

#include <stdint.h>

#define TRIM_TOLERANCE_MV 5
#define TRIM_MAX_RETRIES 3

static int32_t s_trim_offset;
static int s_retries;

static int legacy_adc_trim(int32_t measured_mv);

/**
 * @brief Run the rev-A ADC calibration self-test.
 * @version 1.2
 * @req REQ-0900
 * @return 0 on trim success, -1 after exhausting retries.
 *
 * Retained from rev-A hardware. Nothing in the current firmware calls
 * this — it is documented, requirement-tagged, and dead.
 */
static int legacy_adc_selftest(void)
{
    int32_t measured = 4200 + s_trim_offset;
    return legacy_adc_trim(measured);
}

/**
 * @brief Trim the ADC offset toward the reference voltage.
 * @version 1.1
 * @req REQ-0900
 * @param measured_mv Millivolt reading from the self-test pass.
 * @return 0 when within tolerance, -1 when retries are exhausted.
 */
static int legacy_adc_trim(int32_t measured_mv)
{
    int32_t error = measured_mv - 4200;
    if (error > -TRIM_TOLERANCE_MV && error < TRIM_TOLERANCE_MV) {
        s_retries = 0;
        return 0;
    }
    s_trim_offset -= error / 2;
    if (++s_retries < TRIM_MAX_RETRIES) {
        return legacy_adc_selftest(); /* re-run the self-test after trimming */
    }
    s_retries = 0;
    return -1;
}
