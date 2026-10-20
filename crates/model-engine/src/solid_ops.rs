//! Bounded exact convex Boolean and rigid operations; no approximate or external fallback.
use super::{error, Axis, Body, Result, Q};
use boundary_clip::{Boundary, Plane, Request};

pub(super) fn intersection(id: &str, mut left: Boundary, right: &Boundary) -> Result<Body> {
    let mut volume = String::new();
    // A closed convex solid is the intersection of its outward face half-spaces.
    // The clipper validates each intermediate boundary and its resource limits.
    for face in &right.faces {
        let result = boundary_clip::clip(Request {
            schema_version: 1,
            boundary: left,
            plane: Plane {
                normal: face.normal.clone(),
                offset: face.offset.clone(),
            },
        })
        .map_err(|message| error("invalid_geometry", id, &message))?;
        if result.classification == "empty" {
            return Err(error("empty_solid", id, "Inputs have no common positive volume; they are disjoint or touch only at a face, edge or point"));
        }
        left = result.boundary;
        volume = result.volume;
    }
    Ok(Body {
        feature_id: id.into(),
        components: None,
        polyhedral: None,
        boundary: Some(left),
        analytic: None,
        volume_mm3: volume,
    })
}

pub(super) fn translate(id: &str, boundary: Boundary, delta: &[Q; 3]) -> Result<Body> {
    rigid(id, boundary, delta, |point| point, false)
}

pub(super) fn rotate_quarter(
    id: &str,
    boundary: Boundary,
    axis: Axis,
    turns: i32,
    pivot: &[Q; 3],
) -> Result<Body> {
    let rotate = |mut p: [Q; 3]| {
        for _ in 0..turns {
            let [x, y, z] = p;
            p = match axis {
                Axis::X => [x, -z, y],
                Axis::Y => [z, y, -x],
                Axis::Z => [-y, x, z],
            };
        }
        p
    };
    let rotated = rotate(pivot.clone());
    let delta = std::array::from_fn(|i| &pivot[i] - &rotated[i]);
    rigid(id, boundary, &delta, rotate, false)
}

pub(super) fn mirror(id: &str, boundary: Boundary, normal: &[Q; 3], offset: &Q) -> Result<Body> {
    use num_traits::Zero;
    let squared = crate::topology::dot(normal, normal);
    if squared.is_zero() {
        return Err(error(
            "mirror_normal",
            id,
            "Mirror plane normal must be nonzero",
        ));
    }
    let two = Q::from_integer(2.into());
    let delta = std::array::from_fn(|i| &two * offset * &normal[i] / &squared);
    let reflect = |p: [Q; 3]| {
        let scale = &two * crate::topology::dot(normal, &p) / &squared;
        std::array::from_fn(|i| &p[i] - &normal[i] * &scale)
    };
    rigid(id, boundary, &delta, reflect, true)
}

fn rigid(
    id: &str,
    mut boundary: Boundary,
    delta: &[Q; 3],
    rotate: impl Fn([Q; 3]) -> [Q; 3],
    reverse_orientation: bool,
) -> Result<Body> {
    // These are computed boundary values, already validated upstream, not new
    // 128-bit user literals. The boundary validator checks the resulting budget.
    let value = |s: &str| {
        s.parse::<Q>().map_err(|_| {
            error(
                "invalid_geometry",
                id,
                "Invalid computed boundary coordinate",
            )
        })
    };
    for point in &mut boundary.vertices {
        let transformed = rotate([value(&point[0])?, value(&point[1])?, value(&point[2])?]);
        for axis in 0..3 {
            point[axis] = (&transformed[axis] + &delta[axis]).to_string();
        }
    }
    for face in &mut boundary.faces {
        let normal = rotate([
            value(&face.normal[0])?,
            value(&face.normal[1])?,
            value(&face.normal[2])?,
        ]);
        let shift = (0..3).map(|axis| &normal[axis] * &delta[axis]).sum::<Q>();
        face.offset = (value(&face.offset)? + shift).to_string();
        face.normal = normal.map(|n| n.to_string());
        if reverse_orientation {
            for uses in &mut face.loops {
                uses.reverse();
                for edge in uses {
                    edge.forward = !edge.forward;
                }
            }
        }
    }
    let face = boundary
        .faces
        .first()
        .ok_or_else(|| error("invalid_geometry", id, "Solid has no faces"))?;
    let plane = Plane {
        normal: face.normal.clone(),
        offset: face.offset.clone(),
    };
    // A no-op cut revalidates topology/orientation/volume and rational limits.
    let result = boundary_clip::clip(Request {
        schema_version: 1,
        boundary,
        plane,
    })
    .map_err(|message| error("invalid_geometry", id, &message))?;
    if result.classification == "empty" {
        return Err(error(
            "invalid_geometry",
            id,
            "Rigid operation unexpectedly produced no solid",
        ));
    }
    Ok(Body {
        feature_id: id.into(),
        components: None,
        polyhedral: None,
        boundary: Some(result.boundary),
        analytic: None,
        volume_mm3: result.volume,
    })
}
