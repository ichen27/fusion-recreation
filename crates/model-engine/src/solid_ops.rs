//! Bounded exact convex Boolean operations; no approximate or external fallback.
use super::{error, Body, Result};
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
