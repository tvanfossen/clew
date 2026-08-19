//! Tiny fixture crate for `tests/test_rustdoc.py`.

/// Adds two numbers together.
pub fn add(left: i32, right: i32) -> i32 {
    left + right
}

fn helper(x: i32) -> i32 {
    add(x, 1)
}

pub static MAX_RETRIES: i32 = 3;

fn main() {
    println!("{}", helper(MAX_RETRIES));
}
