//! Exact, bounded XY profiles. No tolerance-based repair or mesh fallback.
use super::{error, identifier, parameter, Model, Result, Q};
use boundary_clip::{Boundary, Edge, Face, Use};
use num_traits::{Signed, Zero};
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet};

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ProfileVertex {
    pub id: String,
    pub x: String,
    pub y: String,
}

#[derive(Debug, Serialize)]
pub struct EvaluatedVertex {
    pub id: String,
    pub position: [String; 3],
}

#[derive(Debug, Serialize)]
pub struct EvaluatedProfile {
    pub feature_id: String,
    pub vertices: Vec<EvaluatedVertex>,
    pub area_mm2: String,
}

pub(super) struct Profile {
    id: String,
    vertex_ids: Vec<String>,
    pub(super) points: Vec<[Q; 2]>,
    pub(super) twice_area: Q,
    pub(super) convex_only: bool,
}

impl Profile {
    pub(super) fn output(self) -> EvaluatedProfile {
        EvaluatedProfile {
            feature_id: self.id,
            vertices: self
                .vertex_ids
                .into_iter()
                .zip(self.points)
                .map(|(id, [x, y])| EvaluatedVertex {
                    id,
                    position: [x.to_string(), y.to_string(), "0".into()],
                })
                .collect(),
            area_mm2: (self.twice_area.abs() / Q::from_integer(2.into())).to_string(),
        }
    }
}

pub(super) fn resolve(m: &Model, id: &str, vertices: &[ProfileVertex]) -> Result<Profile> {
    resolve_mode(m, id, vertices, true)
}
pub(super) fn resolve_planar(m: &Model, id: &str, vertices: &[ProfileVertex]) -> Result<Profile> {
    resolve_mode(m, id, vertices, false)
}
fn resolve_mode(
    m: &Model,
    id: &str,
    vertices: &[ProfileVertex],
    convex_only: bool,
) -> Result<Profile> {
    if !(3..=32).contains(&vertices.len()) {
        return Err(error(
            "profile_limit",
            id,
            "Profiles require 3..32 vertices",
        ));
    }
    let mut ids = BTreeSet::new();
    let mut points = Vec::new();
    for v in vertices {
        identifier(&v.id)?;
        if !ids.insert(&v.id) {
            return Err(error(
                "duplicate_id",
                &v.id,
                "Vertex ID repeats within profile",
            ));
        }
        let point = [parameter(m, &v.x)?, parameter(m, &v.y)?];
        if point
            .iter()
            .any(|q| q.abs() > Q::from_integer(1_000_000.into()))
        {
            return Err(error(
                "coordinate_range",
                &v.id,
                "Profile coordinates must be within +/-1000000 mm",
            ));
        }
        points.push(point);
    }
    let n = points.len();
    let twice_area: Q = (0..n)
        .map(|i| {
            let (a, b) = (&points[i], &points[(i + 1) % n]);
            &a[0] * &b[1] - &b[0] * &a[1]
        })
        .sum();
    if convex_only {
        // Every other vertex must lie strictly on the interior side of every edge.
        // Checking only adjacent turns would incorrectly accept star polygons.
        for i in 0..n {
            let j = (i + 1) % n;
            let (a, b) = (&points[i], &points[j]);
            for (k, c) in points.iter().enumerate() {
                if k == i || k == j {
                    continue;
                }
                let cross = (&b[0] - &a[0]) * (&c[1] - &a[1]) - (&b[1] - &a[1]) * (&c[0] - &a[0]);
                if cross.is_zero() || cross.is_positive() != twice_area.is_positive() {
                    return Err(error("invalid_profile", id, "Expected one strictly convex loop: no repeated points, collinear corners, concavity or crossings"));
                }
            }
        }
    } else {
        validate_simple(&points, &twice_area, id)?;
    }
    Ok(Profile {
        id: id.into(),
        vertex_ids: vertices.iter().map(|v| v.id.clone()).collect(),
        points,
        twice_area,
        convex_only,
    })
}

pub(super) fn extrude(profile: &Profile, height: &Q) -> Boundary {
    let mut points = profile.points.clone();
    if profile.twice_area.is_negative() {
        points.reverse();
    }
    let n = points.len();
    let zero = Q::zero();
    let one = Q::from_integer(1.into());
    let vertices = [&zero, height]
        .into_iter()
        .flat_map(|z| {
            points
                .iter()
                .map(move |p| [p[0].to_string(), p[1].to_string(), z.to_string()])
        })
        .collect();
    let mut edges = Vec::<Edge>::new();
    let mut edge_map = BTreeMap::new();
    let mut faces = Vec::new();
    let mut add_face = |indices: Vec<usize>, normal: [Q; 3], offset: Q| {
        let uses = (0..indices.len())
            .map(|i| {
                let (a, b) = (indices[i], indices[(i + 1) % indices.len()]);
                let key = [a.min(b), a.max(b)];
                let edge = *edge_map.entry(key).or_insert_with(|| {
                    edges.push(Edge {
                        kind: "line".into(),
                        vertices: key,
                    });
                    edges.len() - 1
                });
                Use {
                    edge,
                    forward: a < b,
                }
            })
            .collect();
        faces.push(Face {
            kind: "plane".into(),
            normal: normal.map(|v| v.to_string()),
            offset: offset.to_string(),
            loops: vec![uses],
        });
    };
    add_face(
        (0..n).rev().collect(),
        [zero.clone(), zero.clone(), -&one],
        zero.clone(),
    );
    add_face(
        (n..2 * n).collect(),
        [zero.clone(), zero.clone(), one],
        height.clone(),
    );
    for i in 0..n {
        let j = (i + 1) % n;
        let (a, b) = (&points[i], &points[j]);
        let normal = [&b[1] - &a[1], &a[0] - &b[0], zero.clone()];
        let offset = &normal[0] * &a[0] + &normal[1] * &a[1];
        add_face(vec![i, j, j + n, i + n], normal, offset);
    }
    Boundary {
        vertices,
        edges,
        faces,
    }
}

fn cross(a: &[Q; 2], b: &[Q; 2], c: &[Q; 2]) -> Q {
    (&b[0] - &a[0]) * (&c[1] - &a[1]) - (&b[1] - &a[1]) * (&c[0] - &a[0])
}
fn on_segment(a: &[Q; 2], b: &[Q; 2], p: &[Q; 2]) -> bool {
    cross(a, b, p).is_zero()
        && (0..2).all(|i| {
            p[i] >= a[i].clone().min(b[i].clone()) && p[i] <= a[i].clone().max(b[i].clone())
        })
}
fn intersects(a: &[Q; 2], b: &[Q; 2], c: &[Q; 2], d: &[Q; 2]) -> bool {
    let (ab_c, ab_d, cd_a, cd_b) = (
        cross(a, b, c),
        cross(a, b, d),
        cross(c, d, a),
        cross(c, d, b),
    );
    if on_segment(a, b, c) || on_segment(a, b, d) || on_segment(c, d, a) || on_segment(c, d, b) {
        return true;
    }
    !ab_c.is_zero()
        && !ab_d.is_zero()
        && !cd_a.is_zero()
        && !cd_b.is_zero()
        && ab_c.is_positive() != ab_d.is_positive()
        && cd_a.is_positive() != cd_b.is_positive()
}
fn validate_simple(points: &[[Q; 2]], twice_area: &Q, id: &str) -> Result<()> {
    let fail = || {
        error("invalid_profile",id,"Expected one simple polygon: no crossings, repeated points, overlapping edges or collinear corners")
    };
    let n = points.len();
    if twice_area.is_zero() {
        return Err(fail());
    }
    for i in 0..n {
        if cross(&points[i], &points[(i + 1) % n], &points[(i + 2) % n]).is_zero() {
            return Err(fail());
        }
        for j in i + 1..n {
            if j == i + 1 || (j + 1) % n == i {
                continue;
            }
            if intersects(
                &points[i],
                &points[(i + 1) % n],
                &points[j],
                &points[(j + 1) % n],
            ) {
                return Err(fail());
            }
        }
    }
    Ok(())
}
/// A disk is contained iff its center is inside and it has strict clearance
/// from every boundary segment. Exact rational ray crossing and squared distances.
pub(super) fn contains_disk(points: &[[Q; 2]], x: &Q, y: &Q, r: &Q) -> bool {
    let mut inside = false;
    for i in 0..points.len() {
        let (a, b) = (&points[i], &points[(i + 1) % points.len()]);
        if (&a[1] > y) != (&b[1] > y) {
            let at_x = &a[0] + (y - &a[1]) * (&b[0] - &a[0]) / (&b[1] - &a[1]);
            if x < &at_x {
                inside = !inside;
            }
        }
        let (dx, dy) = (&b[0] - &a[0], &b[1] - &a[1]);
        let (wx, wy) = (x - &a[0], y - &a[1]);
        let length2 = &dx * &dx + &dy * &dy;
        let dot = &wx * &dx + &wy * &dy;
        let distance2 = if dot <= Q::zero() {
            &wx * &wx + &wy * &wy
        } else if dot >= length2 {
            let (vx, vy) = (x - &b[0], y - &b[1]);
            &vx * &vx + &vy * &vy
        } else {
            let c = &dx * &wy - &dy * &wx;
            &c * &c / length2
        };
        if distance2 <= r * r {
            return false;
        }
    }
    inside
}
