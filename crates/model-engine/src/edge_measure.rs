//! Exact length of a revision-scoped native edge; never a tessellation chord.
use crate::{error, topology, Model, Result, Q};
use num_traits::ToPrimitive;
use serde::{Deserialize, Serialize};
use std::collections::BTreeSet;

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Request {
    pub model: Model,
    pub feature_id: String,
    pub edge_index: usize,
}
#[derive(Serialize)]
pub struct Measurement {
    pub feature_id: String,
    pub edge_index: usize,
    pub endpoints_mm: [topology::Coordinates; 2],
    pub curve: topology::Curve,
    pub chord_squared_mm2: String,
    pub chord_mm: String,
    pub length_mm: String,
    pub length_approx_mm: f64,
    pub incident_surfaces: Vec<String>,
    pub patch_seam: bool,
}
fn root(value: &Q) -> String {
    let numerator = value.numer().sqrt();
    let denominator = value.denom().sqrt();
    if &numerator * &numerator == *value.numer() && &denominator * &denominator == *value.denom() {
        Q::new(numerator, denominator).to_string()
    } else {
        format!("sqrt({value})")
    }
}
pub fn measure(request: Request) -> Result<Measurement> {
    let topology = topology::inspect(topology::Request {
        model: request.model,
        feature_id: request.feature_id,
    })?;
    let edge = topology.edges.get(request.edge_index).ok_or_else(|| {
        error(
            "missing_edge",
            &topology.feature_id,
            "Refresh topology and select an edge index at this revision",
        )
    })?;
    let endpoints = edge.vertices.map(|i| topology.vertices[i].clone());
    let delta = topology::sub(
        &topology::point(&endpoints[1])?,
        &topology::point(&endpoints[0])?,
    );
    let squared = topology::dot(&delta, &delta);
    let chord = root(&squared);
    let (length, approx) = match &edge.curve {
        topology::Curve::Line => (chord.clone(), squared.to_f64().unwrap_or(f64::NAN).sqrt()),
        topology::Curve::QuarterCircle { radius, .. } => {
            let coefficient = topology::value(radius)? / Q::from_integer(2.into());
            (
                format!("{coefficient}*pi"),
                coefficient.to_f64().unwrap_or(f64::NAN) * std::f64::consts::PI,
            )
        }
    };
    if !approx.is_finite() {
        return Err(error(
            "measurement_limit",
            &topology.feature_id,
            "Approximate edge length exceeds floating display range",
        ));
    }
    let surfaces: BTreeSet<_> = topology
        .faces
        .iter()
        .filter(|face| {
            face.loops
                .iter()
                .flatten()
                .any(|u| u.edge == request.edge_index)
        })
        .map(|f| f.surface.clone())
        .collect();
    Ok(Measurement {
        feature_id: topology.feature_id,
        edge_index: request.edge_index,
        endpoints_mm: endpoints,
        curve: edge.curve.clone(),
        chord_squared_mm2: squared.to_string(),
        chord_mm: chord,
        length_mm: length,
        length_approx_mm: approx,
        patch_seam: surfaces.len() == 1,
        incident_surfaces: surfaces.into_iter().collect(),
    })
}
