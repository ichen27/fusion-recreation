//! Exact inward planar shells when every retained plane has a rational unit normal.
use crate::topology::{cross, dot, is_zero, point};
use crate::{error, polyhedral, Boundary, Result, Q};
use num_traits::{Signed, Zero};

pub(crate) fn hollow(
    id: &str,
    outer: Boundary,
    thickness: &Q,
    opening: Option<&[String; 3]>,
) -> Result<polyhedral::Solid> {
    let direction = opening
        .map(|values| {
            Ok([
                crate::rational(&values[0], id)?,
                crate::rational(&values[1], id)?,
                crate::rational(&values[2], id)?,
            ])
        })
        .transpose()?;
    if direction.as_ref().is_some_and(is_zero) {
        return Err(error(
            "opening_normal",
            id,
            "Opening direction must be nonzero",
        ));
    }
    let mut planes = Vec::new();
    let mut openings = 0;
    for face in &outer.faces {
        let normal = point(&face.normal)?;
        let opened = direction
            .as_ref()
            .is_some_and(|d| is_zero(&cross(&normal, d)) && dot(&normal, d).is_positive());
        let mut offset = crate::measure::value(&face.offset)?;
        if opened {
            openings += 1;
        } else {
            let length = crate::edge_measure::root(&dot(&normal, &normal))
                .parse::<Q>()
                .map_err(|_| {
                    error(
                        "unsupported_shell",
                        id,
                        "This face needs an irrational plane offset for uniform thickness; only rational-unit-normal planar shells are supported",
                    )
                })?;
            offset -= thickness * length;
        }
        planes.push(boundary_clip::Plane {
            normal: face.normal.clone(),
            offset: offset.to_string(),
        });
    }
    if direction.is_some() && openings != 1 {
        return Err(error(
            "missing_opening",
            id,
            "Opening direction must identify exactly one outward face of the convex input",
        ));
    }
    let mut inner = outer.clone();
    for plane in planes {
        let result = boundary_clip::clip(boundary_clip::Request {
            schema_version: 1,
            boundary: inner,
            plane,
        })
        .map_err(|message| error("invalid_geometry", id, &message))?;
        if result.classification == "empty" {
            return Err(error(
                "shell_thickness",
                id,
                "Thickness leaves no positive-volume interior; reduce the wall thickness",
            ));
        }
        inner = result.boundary;
    }
    let result = polyhedral::Solid::from_convex(outer)?.combine(
        &polyhedral::Solid::from_convex(inner)?,
        polyhedral::Operation::Difference,
    )?;
    if result.volume.is_zero() {
        return Err(error(
            "shell_thickness",
            id,
            "Shell must retain positive material volume",
        ));
    }
    Ok(result)
}
