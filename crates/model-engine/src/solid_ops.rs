//! Bounded exact convex Boolean operations; no approximate or external fallback.
use super::{error, Body, Result, Q};
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
        boundary: Some(left),
        analytic: None,
        volume_mm3: volume,
    })
}

pub(super) fn translate(id: &str, mut boundary: Boundary, delta: &[Q; 3]) -> Result<Body> {
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
        for axis in 0..3 {
            point[axis] = (value(&point[axis])? + &delta[axis]).to_string();
        }
    }
    for face in &mut boundary.faces {
        let shift = (0..3)
            .map(|axis| value(&face.normal[axis]).map(|n| n * &delta[axis]))
            .collect::<Result<Vec<_>>>()?
            .into_iter()
            .sum::<Q>();
        face.offset = (value(&face.offset)? + shift).to_string();
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
            "Translation unexpectedly produced no solid",
        ));
    }
    Ok(Body {
        feature_id: id.into(),
        boundary: Some(result.boundary),
        analytic: None,
        volume_mm3: result.volume,
    })
}
