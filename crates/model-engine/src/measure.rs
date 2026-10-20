//! Exact geometric volume moments of validated planar solids, without density.
use super::{error, profile, Boundary, Feature, Model, Result, Q};
use num_traits::{Signed, Zero};
use serde::{Deserialize, Serialize};

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Request {
    pub model: Model,
    pub feature_id: String,
}

#[derive(Serialize)]
pub struct Measurements {
    pub feature_id: String,
    pub volume_mm3: String,
    pub bounds_mm: [[String; 3]; 2],
    pub centroid_mm: [String; 3],
    /// Integral (r^2 I - r r^T) dV about centroid, in global XYZ axes.
    /// Multiply by a uniform mass density to obtain a mass inertia tensor.
    pub centroidal_volume_inertia_mm5: [[String; 3]; 3],
}

pub(super) fn bounded(q: &Q) -> Result<()> {
    if q.numer().bits() > 8192 || q.denom().bits() > 8192 {
        return Err(error(
            "measurement_limit",
            "measurement",
            "Exact volume moments exceed 8192-bit budget",
        ));
    }
    Ok(())
}
pub(super) fn value(s: &str) -> Result<Q> {
    let q: Q = s.parse().map_err(|_| {
        error(
            "invalid_geometry",
            "measurement",
            "Invalid exact coordinate",
        )
    })?;
    bounded(&q)?;
    Ok(q)
}
fn q(n: i32) -> Q {
    Q::from_integer(n.into())
}

pub fn measure(request: Request) -> Result<Measurements> {
    let evaluated = super::evaluate(super::Request {
        schema_version: 1,
        model: request.model,
        operations: vec![],
        preserve: vec![],
    })?;
    let id = &request.feature_id;
    let body = evaluated
        .bodies
        .into_iter()
        .find(|b| &b.feature_id == id)
        .ok_or_else(|| error("missing_body", id, "Select a terminal solid"))?;
    if let Some(shape) = &body.analytic {
        if shape.revolution.is_some()
            || shape.outer_circle.is_some()
            || !shape.holes.is_empty()
            || shape.placement.is_some()
        {
            return crate::measure_curved::measure(id, shape, &body.volume_mm3);
        }
    }
    let boundary = if let Some(boundary) = body.boundary {
        boundary
    } else {
        // Validated simple source prisms need no floating triangulation or cell split.
        let model = &evaluated.model;
        match model.features.iter().find(|f| f.id() == id) {
            Some(Feature::Extrude { profile: source, height, .. }) => {
                let outline = match model.features.iter().find(|f| f.id() == source) {
                    Some(Feature::PlanarProfile { id, vertices }) => profile::resolve_planar(model, id, vertices)?,
                    Some(Feature::PolygonProfile { id, vertices }) => profile::resolve(model, id, vertices)?,
                    _ => return Err(error("unsupported_measurement", id, "Expected a validated planar profile")),
                };
                profile::extrude(&outline, &super::positive(model, height)?)
            }
            _ => return Err(error("unsupported_measurement", id, "Exact moments currently require unperforated planar stock or planar operation results")),
        }
    };
    moments(id, &boundary, &value(&body.volume_mm3)?)
}

fn moments(id: &str, boundary: &Boundary, expected_volume: &Q) -> Result<Measurements> {
    let points = boundary
        .vertices
        .iter()
        .map(|p| Ok([value(&p[0])?, value(&p[1])?, value(&p[2])?]))
        .collect::<Result<Vec<_>>>()?;
    let mut volume = q(0);
    let mut first: [Q; 3] = std::array::from_fn(|_| q(0));
    let mut second: [[Q; 3]; 3] = std::array::from_fn(|_| std::array::from_fn(|_| q(0)));
    for face in &boundary.faces {
        for ring in &face.loops {
            let ids: Vec<_> = ring
                .iter()
                .map(|e| boundary.edges[e.edge].vertices[usize::from(!e.forward)])
                .collect();
            // Signed triangle fans integrate oriented loops, including concave
            // outlines and hole loops. They are integration chains, not meshes.
            for i in 1..ids.len() - 1 {
                let [a, b, c] = [&points[ids[0]], &points[ids[i]], &points[ids[i + 1]]];
                let determinant = &a[0] * (&b[1] * &c[2] - &b[2] * &c[1])
                    - &a[1] * (&b[0] * &c[2] - &b[2] * &c[0])
                    + &a[2] * (&b[0] * &c[1] - &b[1] * &c[0]);
                let v = determinant / q(6);
                let sums: [Q; 3] = std::array::from_fn(|j| &a[j] + &b[j] + &c[j]);
                volume += &v;
                bounded(&volume)?;
                for j in 0..3 {
                    first[j] += &v * &sums[j] / q(4);
                    bounded(&first[j])?;
                    for k in 0..3 {
                        second[j][k] += &v
                            * (&sums[j] * &sums[k] + &a[j] * &a[k] + &b[j] * &b[k] + &c[j] * &c[k])
                            / q(20);
                        bounded(&second[j][k])?;
                    }
                }
            }
        }
    }
    if !volume.is_positive() || &volume != expected_volume {
        return Err(error(
            "invalid_geometry",
            id,
            "Integrated volume does not match validated solid",
        ));
    }
    let center: [Q; 3] = std::array::from_fn(|j| &first[j] / &volume);
    let central: [[Q; 3]; 3] = std::array::from_fn(|j| {
        std::array::from_fn(|k| &second[j][k] - &volume * &center[j] * &center[k])
    });
    let trace: Q = (0..3).map(|j| &central[j][j]).sum();
    let inertia: [[Q; 3]; 3] = std::array::from_fn(|j| {
        std::array::from_fn(|k| {
            if j == k {
                &trace - &central[j][k]
            } else {
                -&central[j][k]
            }
        })
    });
    for v in center.iter().chain(inertia.iter().flatten()) {
        bounded(v)?;
    }
    if (0..3).any(|j| inertia[j][j] <= Q::zero()) {
        return Err(error(
            "invalid_geometry",
            id,
            "Non-positive centroidal volume inertia",
        ));
    }
    let bounds: [[Q; 3]; 2] = std::array::from_fn(|side| {
        std::array::from_fn(|axis| {
            let values = points.iter().map(|p| p[axis].clone());
            if side == 0 {
                values.min().unwrap()
            } else {
                values.max().unwrap()
            }
        })
    });
    Ok(Measurements {
        feature_id: id.into(),
        volume_mm3: volume.to_string(),
        bounds_mm: bounds.map(|p| p.map(|v| v.to_string())),
        centroid_mm: center.map(|v| v.to_string()),
        centroidal_volume_inertia_mm5: inertia.map(|r| r.map(|v| v.to_string())),
    })
}
