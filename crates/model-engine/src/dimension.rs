//! User-facing dimension literals canonicalize to exact rational millimeters.
//! Native models and dimensionless feature literals retain the strict rational schema.
use crate::{error, rational, Result, Q};
use num_bigint::BigInt;

pub(crate) fn parse(input: &str, id: &str) -> Result<Q> {
    let invalid = || {
        error("invalid_number", id, "Use a decimal, integer or fraction, optionally followed by mm, cm, m, in or ft; exact components must fit 128 bits")
    };
    if input.len() > 96 {
        return Err(invalid());
    }
    let lower = input.trim().to_ascii_lowercase();
    let units = [
        ("mm", 1, 1),
        ("cm", 10, 1),
        ("in", 127, 5),
        ("ft", 1524, 5),
        ("m", 1000, 1),
    ];
    let (number, numerator, denominator) = units
        .iter()
        .find_map(|(unit, n, d)| lower.strip_suffix(unit).map(|v| (v.trim_end(), *n, *d)))
        .unwrap_or((&lower, 1, 1));
    if number.starts_with("+-") {
        return Err(invalid());
    }
    let number = number.strip_prefix('+').unwrap_or(number);
    if number.is_empty() || number.len() > 80 {
        return Err(invalid());
    }
    let value = if let Some((whole, fraction)) = number.split_once('.') {
        let digits = whole.strip_prefix('-').unwrap_or(whole);
        if (digits.is_empty() && fraction.is_empty())
            || !digits.bytes().all(|b| b.is_ascii_digit())
            || !fraction.bytes().all(|b| b.is_ascii_digit())
        {
            return Err(invalid());
        }
        let coefficient = format!("{whole}{fraction}");
        let divisor = BigInt::from(10).pow(fraction.len() as u32);
        rational(&format!("{coefficient}/{divisor}"), id).map_err(|_| invalid())?
    } else {
        rational(number, id).map_err(|_| invalid())?
    };
    let result = value * Q::new(numerator.into(), denominator.into());
    // Conversion can enlarge a numerator, so recheck the canonical storage budget.
    rational(&result.to_string(), id).map_err(|_| invalid())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn exact_decimal_and_unit_conversions() {
        for (input, expected) in [
            ("12.5", "25/2"),
            (".5", "1/2"),
            ("-.125", "-1/8"),
            ("+1.", "1"),
            ("1/2 in", "127/10"),
            ("1 IN", "127/5"),
            ("2.54 cm", "127/5"),
            ("0.001m", "1"),
            ("-1/12 ft", "-127/5"),
            (" -0.00 mm ", "0"),
            ("1/-2 mm", "-1/2"),
        ] {
            assert_eq!(parse(input, "p").unwrap().to_string(), expected, "{input}");
        }
    }
    #[test]
    fn reject_ambiguous_nonfinite_and_over_budget_inputs() {
        for input in [
            "", ".", "-.", "1.2.3", "1.2/3", "1/0", "1e3", "NaN", "inf", "1,5", "1 cm mm", "1 / 2",
            "1yd", "+-1", "+-1.2", "1+2", "1.0e2", "1 2", "1\"", "1e-3 m",
        ] {
            assert_eq!(
                parse(input, "p").unwrap_err().code,
                "invalid_number",
                "{input}"
            );
        }
        assert!(parse(&format!("0.{}1", "0".repeat(39)), "p").is_err());
        assert!(parse(&format!("{} m", (BigInt::from(1) << 127) - 1), "p").is_err());
    }
}
