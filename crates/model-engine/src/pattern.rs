//! Exact bounded linear material patterns; source plus translated copies form a union.
use crate::{error, polyhedral, solid_ops, Result, Q};
use num_traits::{Signed, Zero};

pub(crate) fn linear(
    id: &str,
    source: polyhedral::Solid,
    count: usize,
    step: &[Q; 3],
) -> Result<polyhedral::Solid> {
    if !(1..=16).contains(&count) {
        return Err(error(
            "pattern_count",
            id,
            "Pattern count must be an integer from 1 through 16, including the original",
        ));
    }
    if count > 1 && step.iter().all(Zero::is_zero) {
        return Err(error(
            "pattern_step",
            id,
            "Repeated copies need a nonzero step vector",
        ));
    }
    let span = Q::from_integer((count - 1).into());
    if step.iter().any(|q| {
        q.abs() > Q::from_integer(1_000_000.into())
            || (q * &span).abs() > Q::from_integer(1_000_000.into())
    }) {
        return Err(error(
            "pattern_range",
            id,
            "Step components and total pattern displacement must stay within +/-1000000 mm",
        ));
    }
    let mut result = source.clone();
    for index in 1..count {
        let factor = Q::from_integer(index.into());
        let delta = std::array::from_fn(|i| &step[i] * &factor);
        let copy = source.transform(|cell| {
            solid_ops::translate(id, cell, &delta)?
                .boundary
                .ok_or_else(|| {
                    error(
                        "invalid_geometry",
                        id,
                        "Pattern translation lost its planar boundary",
                    )
                })
        })?;
        result = result.combine(&copy, polyhedral::Operation::Union)?;
    }
    Ok(result)
}
