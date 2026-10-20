//! Exact orientation-preserving signed-axis placements for analytic stock.
use crate::{error, Axis, Body, Result, Q};
use serde::Serialize;

#[derive(Clone, Debug, Serialize)]
pub struct Placement {
    /// Rows of an orthogonal signed-permutation matrix: world = axes * local + origin.
    pub axes: [[i32; 3]; 3],
    pub origin: [String; 3],
}

pub(crate) fn rotate<T: Clone + std::ops::Neg<Output = T>>(
    mut p: [T; 3],
    axis: Axis,
    turns: i32,
) -> [T; 3] {
    for _ in 0..turns {
        let [x, y, z] = p;
        p = match axis {
            Axis::X => [x, -z, y],
            Axis::Y => [z, y, -x],
            Axis::Z => [-y, x, z],
        };
    }
    p
}

pub(crate) fn analytic(
    body: &Body,
    id: &str,
    delta: &[Q; 3],
    rotation: Option<(Axis, i32)>,
) -> Result<Option<Body>> {
    let Some(shape) = &body.analytic else {
        return Ok(None);
    };
    // Preserve the established boundary route for ordinary polygon prisms.
    if shape.revolution.is_none()
        && shape.outer_circle.is_none()
        && shape.holes.is_empty()
        && shape.placement.is_none()
    {
        return Ok(None);
    }
    let mut shape = shape.clone();
    let mut placement = shape.placement.take().unwrap_or(Placement {
        axes: [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
        origin: ["0".into(), "0".into(), "0".into()],
    });
    let mut origin: [Q; 3] = [
        placement.origin[0]
            .parse()
            .map_err(|_| error("invalid_geometry", id, "Invalid placement"))?,
        placement.origin[1]
            .parse()
            .map_err(|_| error("invalid_geometry", id, "Invalid placement"))?,
        placement.origin[2]
            .parse()
            .map_err(|_| error("invalid_geometry", id, "Invalid placement"))?,
    ];
    if let Some((axis, turns)) = rotation {
        origin = rotate(origin, axis, turns);
        for col in 0..3 {
            let column = rotate(
                std::array::from_fn(|row| placement.axes[row][col]),
                axis,
                turns,
            );
            for (row, value) in column.into_iter().enumerate() {
                placement.axes[row][col] = value;
            }
        }
    }
    for i in 0..3 {
        origin[i] += &delta[i];
        if origin[i].numer().bits() > 1024 || origin[i].denom().bits() > 1024 {
            return Err(error(
                "placement_limit",
                id,
                "Computed placement exceeds 1024 bits",
            ));
        }
    }
    placement.origin = origin.map(|q| q.to_string());
    shape.placement = Some(placement);
    Ok(Some(Body {
        feature_id: id.into(),
        components: None,
        polyhedral: None,
        boundary: None,
        analytic: Some(shape),
        volume_mm3: body.volume_mm3.clone(),
    }))
}
