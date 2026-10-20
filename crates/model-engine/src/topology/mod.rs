//! Explicit internally generated line/quarter-circle topology. Not an import parser.
mod build;
mod validate;
use crate::{error, Model, Result, Q};
use num_traits::Zero;
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;
pub(super) type Point = [Q; 3];
pub type Coordinates = [String; 3];
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Request {
    pub model: Model,
    pub feature_id: String,
}
#[derive(Clone, PartialEq, Serialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum Curve {
    Line,
    QuarterCircle {
        center: Coordinates,
        axis: [i32; 3],
        radius: String,
    },
}
#[derive(Clone, Serialize)]
pub struct Edge {
    pub vertices: [usize; 2],
    pub curve: Curve,
}
#[derive(Clone, Copy, Serialize)]
pub struct Use {
    pub edge: usize,
    pub forward: bool,
}
#[derive(Clone, Serialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum Surface {
    Plane {
        normal: Coordinates,
        offset: String,
    },
    ConicalFrustum {
        origin: Coordinates,
        axis: [i32; 3],
        bottom_radius: String,
        top_radius: String,
        height: String,
        #[serde(skip_serializing_if = "is_false")]
        inward: bool,
    },
    Cylinder {
        origin: Coordinates,
        axis: [i32; 3],
        radius: String,
        inward: bool,
    },
}
fn is_false(value: &bool) -> bool {
    !value
}
#[derive(Clone, Serialize)]
pub struct SurfaceRecord {
    pub owner_feature: String,
    #[serde(flatten)]
    pub geometry: Surface,
}
#[derive(Clone, Serialize)]
pub struct Face {
    pub id: String,
    pub surface: String,
    pub loops: Vec<Vec<Use>>,
}
#[derive(Clone, Serialize)]
pub struct Topology {
    pub feature_id: String,
    pub naming: &'static str,
    pub vertices: Vec<Coordinates>,
    pub edges: Vec<Edge>,
    pub surfaces: BTreeMap<String, SurfaceRecord>,
    pub faces: Vec<Face>,
    pub components: Vec<Vec<usize>>,
    pub shells: Vec<Vec<usize>>,
    pub shell_euler: Vec<i32>,
}
pub(super) fn fail(message: &str) -> crate::Error {
    error("invalid_topology", "boundary", message)
}
pub(super) fn q(n: i32) -> Q {
    Q::from_integer(n.into())
}
pub(super) fn value(text: &str) -> Result<Q> {
    let result: Q = text
        .parse()
        .map_err(|_| fail("Invalid exact coefficient"))?;
    if result.numer().bits() > 8192 || result.denom().bits() > 8192 {
        return Err(error(
            "topology_limit",
            "boundary",
            "Exact coefficient exceeds 8192 bits",
        ));
    }
    Ok(result)
}
pub(super) fn point(p: &Coordinates) -> Result<Point> {
    Ok([value(&p[0])?, value(&p[1])?, value(&p[2])?])
}
pub(super) fn output(p: &Point) -> Coordinates {
    p.clone().map(|x| x.to_string())
}
pub(super) fn sub(a: &Point, b: &Point) -> Point {
    std::array::from_fn(|i| &a[i] - &b[i])
}
pub(super) fn dot(a: &Point, b: &Point) -> Q {
    (0..3).map(|i| &a[i] * &b[i]).sum()
}
pub(super) fn cross(a: &Point, b: &Point) -> Point {
    std::array::from_fn(|i| &a[(i + 1) % 3] * &b[(i + 2) % 3] - &a[(i + 2) % 3] * &b[(i + 1) % 3])
}
pub(super) fn axis(a: [i32; 3]) -> Result<Point> {
    if a.iter().any(|v| !(-1..=1).contains(v)) || a.iter().map(|v| v * v).sum::<i32>() != 1 {
        return Err(fail("Expected a signed coordinate axis"));
    }
    Ok(a.map(q))
}
pub fn inspect(request: Request) -> Result<Topology> {
    let evaluated = crate::evaluate(crate::Request {
        schema_version: 1,
        model: request.model,
        operations: vec![],
        preserve: vec![],
    })?;
    let body = evaluated
        .bodies
        .into_iter()
        .find(|b| b.feature_id == request.feature_id)
        .ok_or_else(|| {
            error(
                "missing_body",
                &request.feature_id,
                "Select a terminal solid",
            )
        })?;
    let mut topology = build::body(&evaluated.model, &body)?;
    let (shells, euler) = validate::check(&topology)?;
    if let Some(shape) = &body.analytic {
        let through = if let Some(profile) = &shape.revolution {
            usize::from(!profile.axis_contact)
        } else if shape.hole_depth.is_none() {
            shape.holes.len()
        } else {
            0
        };
        if euler != vec![2 - 2 * through as i32] {
            return Err(fail("Analytic genus does not match its through apertures"));
        }
    }
    topology.shells = shells;
    topology.shell_euler = euler;
    Ok(topology)
}
/// Disposable tessellation roles resolve through the same native boundary builder.
/// Polygon wall order is the normalized analytic outline order used by both builders.
pub(crate) fn mesh_surfaces(model: &Model, body: &crate::Body) -> Result<BTreeMap<String, String>> {
    let topology = build::body(model, body)?;
    let mut names = BTreeMap::new();
    for name in topology.surfaces.keys() {
        let role = if body.analytic.is_some() {
            name.split('/').skip(2).collect::<Vec<_>>().join("/")
        } else {
            name.clone()
        };
        names.insert(role, name.clone());
    }
    if let Some(shape) = &body.analytic {
        if shape.outer_circle.is_none() {
            for (i, face) in topology.faces.iter().take(shape.outer.len()).enumerate() {
                names.insert(format!("outer/side/{i}"), face.surface.clone());
            }
        }
    }
    Ok(names)
}

pub(crate) fn for_body(model: &Model, body: &crate::Body) -> Result<Topology> {
    let mut topology = build::body(model, body)?;
    let (shells, euler) = validate::check(&topology)?;
    topology.shells = shells;
    topology.shell_euler = euler;
    Ok(topology)
}

pub(super) fn reverse(ring: &[Use]) -> Vec<Use> {
    ring.iter()
        .rev()
        .map(|u| Use {
            edge: u.edge,
            forward: !u.forward,
        })
        .collect()
}
pub(super) fn is_zero(p: &Point) -> bool {
    p.iter().all(Zero::is_zero)
}

#[cfg(test)]
mod tests;
