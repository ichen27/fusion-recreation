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
    pub(super) vertex_ids: Vec<String>,
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
        if !strictly_convex(&points, &twice_area) {
            return Err(error("invalid_profile", id, "Expected one strictly convex loop: no repeated points, collinear corners, concavity or crossings"));
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

// Every other vertex must lie strictly inside every oriented edge. This also
// rejects star polygons, unlike testing only consecutive turns.
fn strictly_convex(points: &[[Q; 2]], twice_area: &Q) -> bool {
    (0..points.len()).all(|i| {
        let j = (i + 1) % points.len();
        points.iter().enumerate().all(|(k, c)| {
            if k == i || k == j {
                return true;
            }
            let turn = cross(&points[i], &points[j], c);
            !turn.is_zero() && turn.is_positive() == twice_area.is_positive()
        })
    })
}

/// Exact convex decomposition of an already validated simple profile.
/// Ear clipping uses rational orientation and containment predicates. Display
/// triangulation is never used to define native geometry.
pub(super) fn convex_cells(profile: &Profile, height: &Q) -> Result<Vec<Boundary>> {
    let mut points = profile.points.clone();
    if profile.twice_area.is_negative() {
        points.reverse();
    }
    let mut remaining: Vec<usize> = (0..points.len()).collect();
    let mut triangles = Vec::new();
    while remaining.len() > 3 {
        let ear = (0..remaining.len())
            .find(|&i| {
                let [a, b, c] = [
                    remaining[(i + remaining.len() - 1) % remaining.len()],
                    remaining[i],
                    remaining[(i + 1) % remaining.len()],
                ];
                if !cross(&points[a], &points[b], &points[c]).is_positive() {
                    return false;
                }
                !remaining.iter().copied().any(|p| {
                    ![a, b, c].contains(&p)
                        && cross(&points[a], &points[b], &points[p]) >= Q::zero()
                        && cross(&points[b], &points[c], &points[p]) >= Q::zero()
                        && cross(&points[c], &points[a], &points[p]) >= Q::zero()
                })
            })
            .ok_or_else(|| {
                error(
                    "invalid_profile",
                    &profile.id,
                    "Exact convex decomposition failed",
                )
            })?;
        triangles.push([
            remaining[(ear + remaining.len() - 1) % remaining.len()],
            remaining[ear],
            remaining[(ear + 1) % remaining.len()],
        ]);
        remaining.remove(ear);
    }
    triangles.push([remaining[0], remaining[1], remaining[2]]);
    let mut area = Q::zero();
    let mut cells = Vec::new();
    for indices in triangles {
        let vertices = indices.map(|i| points[i].clone());
        let twice_area = cross(&vertices[0], &vertices[1], &vertices[2]);
        if !twice_area.is_positive() {
            return Err(error(
                "invalid_profile",
                &profile.id,
                "Degenerate exact decomposition cell",
            ));
        }
        area += &twice_area;
        let triangle = Profile {
            id: profile.id.clone(),
            vertex_ids: vec![],
            points: vertices.into(),
            twice_area,
            convex_only: true,
        };
        cells.push(extrude(&triangle, height));
    }
    if area != profile.twice_area.abs() {
        return Err(error(
            "invalid_profile",
            &profile.id,
            "Exact decomposition area mismatch",
        ));
    }
    Ok(cells)
}

pub(super) fn is_convex(profile: &Profile) -> bool {
    strictly_convex(&profile.points, &profile.twice_area)
}

pub(super) fn convex_boundary(
    profile: &Profile,
    height: &Q,
    input: &str,
    operation: &str,
) -> Result<Boundary> {
    if !strictly_convex(&profile.points, &profile.twice_area) {
        return Err(error(
            "unsupported_reference",
            input,
            &format!("{operation} require convex stock; the input sketch has inward corners"),
        ));
    }
    Ok(extrude(profile, height))
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

/// The boundary is exact only when all corresponding side quadrilaterals are
/// planar and bound a convex solid. Do not silently triangulate a curved side.
pub(super) fn loft(id: &str, bottom: &Profile, top: &Profile, height: &Q) -> Result<Boundary> {
    let fail = |message: &str| error("unsupported_loft", id, message);
    if !is_convex(bottom) || !is_convex(top) {
        return Err(fail(
            "Planar loft requires two strictly convex polygon profiles",
        ));
    }
    let n = bottom.points.len();
    if n != top.points.len()
        || bottom.vertex_ids.iter().collect::<BTreeSet<_>>() != top.vertex_ids.iter().collect()
    {
        return Err(fail("Loft profiles must have the same named vertex IDs"));
    }
    let mut names = bottom.vertex_ids.clone();
    if bottom.twice_area.is_negative() {
        names.reverse();
    }
    let indices: Vec<_> = names
        .iter()
        .map(|name| top.vertex_ids.iter().position(|v| v == name).unwrap())
        .collect();
    for i in 0..n {
        let a = indices[i];
        let b = indices[(i + 1) % n];
        if (a + 1) % n != b && (b + 1) % n != a {
            return Err(fail(
                "Named loft vertices must preserve profile edge adjacency",
            ));
        }
    }
    let mut boundary = extrude(bottom, height);
    for (i, index) in indices.into_iter().enumerate() {
        let point = &top.points[index];
        boundary.vertices[n + i] = [
            point[0].to_string(),
            point[1].to_string(),
            height.to_string(),
        ];
    }
    let points: Vec<[Q; 3]> = boundary
        .vertices
        .iter()
        .map(|p| p.clone().map(|v| v.parse().unwrap()))
        .collect();
    for face in &mut boundary.faces {
        let vertices: Vec<_> = face.loops[0]
            .iter()
            .map(|u| boundary.edges[u.edge].vertices[usize::from(!u.forward)])
            .collect();
        let a = &points[vertices[0]];
        let b: [Q; 3] = std::array::from_fn(|i| &points[vertices[1]][i] - &a[i]);
        let c: [Q; 3] = std::array::from_fn(|i| &points[vertices[2]][i] - &a[i]);
        let normal = [
            &b[1] * &c[2] - &b[2] * &c[1],
            &b[2] * &c[0] - &b[0] * &c[2],
            &b[0] * &c[1] - &b[1] * &c[0],
        ];
        let dot = |p: &[Q; 3]| (0..3).map(|i| &normal[i] * &p[i]).sum::<Q>();
        let offset = dot(a);
        if normal.iter().all(Zero::is_zero) || vertices.iter().any(|i| dot(&points[*i]) != offset) {
            return Err(fail("Corresponding loft edges form a nonplanar or degenerate side; curved/twisted lofts are unsupported"));
        }
        if points.iter().any(|p| dot(p) > offset) {
            return Err(fail(
                "Corresponding loft profiles must form a convex solid without twists",
            ));
        }
        face.normal = normal.map(|v| v.to_string());
        face.offset = offset.to_string();
    }
    Ok(boundary)
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
