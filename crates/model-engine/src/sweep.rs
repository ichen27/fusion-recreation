//! Exact straight translations of an XY polygon; no sampled path or twist.
use crate::{error, profile, Result, Q};
use boundary_clip::Boundary;
use num_traits::{Signed, Zero};

pub(crate) fn cells(id: &str, source: &profile::Profile, delta: &[Q; 3]) -> Result<Vec<Boundary>> {
    if delta[2].is_zero() {
        return Err(error("sweep_direction", id, "A sweep from an XY profile needs nonzero Z displacement; an in-plane sweep has no solid volume"));
    }
    let bound = Q::from_integer(1_000_000.into());
    if delta.iter().any(|v| v.abs() > bound)
        || source
            .points
            .iter()
            .any(|p| (0..2).any(|i| (&p[i] + &delta[i]).abs() > bound))
    {
        return Err(error(
            "coordinate_range",
            id,
            "Sweep displacement and resulting coordinates must remain within +/-1000000 mm",
        ));
    }
    let unit = Q::from_integer(1.into());
    let mut result = if profile::is_convex(source) {
        vec![profile::extrude(source, &unit)]
    } else {
        profile::convex_cells(source, &unit)?
    };
    let number = |s: &str| {
        s.parse::<Q>()
            .map_err(|_| error("invalid_geometry", id, "Invalid computed sweep coordinate"))
    };
    for cell in &mut result {
        // Affine image of the disjoint exact unit prisms. The inverse transpose
        // transforms supporting planes; negative determinant reverses face loops.
        for point in &mut cell.vertices {
            let [x, y, z] = [number(&point[0])?, number(&point[1])?, number(&point[2])?];
            *point = [x + &z * &delta[0], y + &z * &delta[1], z * &delta[2]].map(|v| v.to_string());
        }
        for face in &mut cell.faces {
            let [nx, ny, nz] = [
                number(&face.normal[0])?,
                number(&face.normal[1])?,
                number(&face.normal[2])?,
            ];
            let axial = (nz - &nx * &delta[0] - &ny * &delta[1]) / &delta[2];
            face.normal = [nx, ny, axial].map(|v| v.to_string());
            if delta[2].is_negative() {
                for ring in &mut face.loops {
                    ring.reverse();
                    for edge in ring {
                        edge.forward = !edge.forward;
                    }
                }
            }
        }
    }
    Ok(result)
}
