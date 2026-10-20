//! Read-only positive-volume overlap of two validated planar terminal bodies.
use crate::{error, Boundary, Model, Result, Q};
use num_traits::{Signed, Zero};
use serde::{Deserialize, Serialize};

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Request {
    pub model: Model,
    pub left: String,
    pub right: String,
}
#[derive(Serialize)]
pub struct Interference {
    pub left: String,
    pub right: String,
    pub positive_volume_overlap: bool,
    pub overlap_volume_mm3: String,
}
fn cells(model: &Model, geometry: &crate::rebuild::Geometry, id: &str) -> Result<Vec<Boundary>> {
    if geometry.consumed.contains(id) || !geometry.evaluated.contains_key(id) {
        return Err(error("missing_body", id, "Select a terminal solid"));
    }
    if let Some(solid) =
        crate::polyhedral_input(model, &geometry.profiles, &geometry.evaluated, id)?
    {
        return Ok(solid.cells);
    }
    match crate::convex_input(model, &geometry.profiles, &geometry.evaluated, id, "interference") {
        Ok(boundary) => Ok(vec![boundary]),
        Err(e) if e.code == "unsupported_reference" => Err(error(
            "unsupported_interference", id,
            "Positive-volume interference currently requires unperforated planar stock or planar operation results; curved/perforated stock is unsupported",
        )),
        Err(e) => Err(e),
    }
}
pub(super) fn bounds(boundary: &Boundary) -> Result<[[Q; 3]; 2]> {
    let points = boundary
        .vertices
        .iter()
        .map(crate::topology::point)
        .collect::<Result<Vec<_>>>()?;
    let first = points
        .first()
        .ok_or_else(|| error("invalid_geometry", "interference", "Empty cell"))?;
    let mut bounds = [first.clone(), first.clone()];
    for point in &points[1..] {
        for (axis, value) in point.iter().enumerate() {
            bounds[0][axis] = bounds[0][axis].clone().min(value.clone());
            bounds[1][axis] = bounds[1][axis].clone().max(value.clone());
        }
    }
    Ok(bounds)
}
pub(super) fn prepare(request: &Request) -> Result<(Vec<Boundary>, Vec<Boundary>)> {
    if request.left == request.right {
        return Err(error(
            "invalid_pair",
            "interference",
            "Choose two distinct terminal bodies",
        ));
    }
    let geometry = crate::evaluate_geometry(&request.model)?;
    let left = cells(&request.model, &geometry, &request.left)?;
    let right = cells(&request.model, &geometry, &request.right)?;
    Ok((left, right))
}
pub fn inspect(request: Request) -> Result<Interference> {
    let (left, right) = prepare(&request)?;
    let left_bounds = left.iter().map(bounds).collect::<Result<Vec<_>>>()?;
    let right_bounds = right.iter().map(bounds).collect::<Result<Vec<_>>>()?;
    let mut volume = Q::zero();
    // Backing cells have disjoint interiors within each body. Their pairwise
    // intersections therefore partition the common volume without double counting.
    // No merged boundary is required, so contact-only pieces are not manufactured.
    for (a, ab) in left.iter().zip(&left_bounds) {
        for (b, bb) in right.iter().zip(&right_bounds) {
            if (0..3).any(|i| ab[1][i] <= bb[0][i] || bb[1][i] <= ab[0][i]) {
                continue;
            }
            match crate::solid_ops::intersection("interference", a.clone(), b) {
                Ok(common) => {
                    volume += crate::measure::value(&common.volume_mm3)?;
                    crate::measure::bounded(&volume)?;
                }
                Err(e) if e.code == "empty_solid" => {}
                Err(e) => return Err(e),
            }
        }
    }
    Ok(Interference {
        left: request.left,
        right: request.right,
        positive_volume_overlap: volume.is_positive(),
        overlap_volume_mm3: volume.to_string(),
    })
}
