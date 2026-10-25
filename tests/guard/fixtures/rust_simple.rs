//! Sensor access for the fixture crate.
//! @version 1

use std::sync::Mutex;

/// Read the raw temperature.
///
/// Longer prose that is not part of the summary.
///
/// @version 2
/// @req REQ-SENSE-001
#[inline]
#[must_use]
pub fn read_temperature(channel: u8) -> u16 {
    u16::from(channel) * 2
}

/** Reset the sensor.
 * @version 1
 * @req REQ-SENSE-002
 */
pub fn reset() {}

pub fn undocumented() {}

/// A sensor handle.
pub struct Sensor {
    lock: Mutex<u8>,
}

impl Sensor {
    /// Build a sensor.
    /// @version 1
    /// @req REQ-SENSE-003
    pub fn new() -> Self {
        Sensor { lock: Mutex::new(0) }
    }

    /// @version 1
    /// @utility
    fn no_summary(&self) {}
}

/// Things that can be calibrated.
pub trait Calibrate {
    /// A required method: a declaration, never checked.
    fn calibrate(&mut self);

    /// Default calibration offset.
    /// @version 1
    /// @utility
    fn offset(&self) -> () {}
}

#[cfg(test)]
mod tests {
    #[test]
    fn untagged_test_is_not_gated() {}
}
