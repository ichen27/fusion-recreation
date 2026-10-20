//! Disposable float64 tessellation. Failure never invalidates an exact saved model.
use crate::{error, validate, Body, Model, Result, Q};
use num_traits::ToPrimitive;
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Request {
    pub model: Model,
    pub feature_id: String,
    pub segments: usize,
    #[serde(default)]
    pub include_surfaces: bool,
}
#[derive(Serialize)]
pub struct Mesh {
    pub vertices: Vec<[f64; 3]>,
    pub triangles: Vec<[usize; 3]>,
    pub edges: Vec<[usize; 2]>,
    pub max_radial_error_mm: f64,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub triangle_surfaces: Option<Vec<String>>,
}
impl Mesh {
    pub(super) fn triangle(&mut self, triangle: [usize; 3], surface: &str) {
        self.triangles.push(triangle);
        if let Some(surfaces) = &mut self.triangle_surfaces {
            surfaces.push(surface.into());
        }
    }
}
pub(super) fn value(s: &str) -> Result<f64> {
    // These are computed, already validated coordinates, not user literals.
    let q: Q = s
        .parse()
        .map_err(|_| error("tessellation_failed", "mesh", "Invalid computed coordinate"))?;
    if q.numer().bits() > 1024 || q.denom().bits() > 1024 {
        return Err(error(
            "tessellation_failed",
            "mesh",
            "Computed coordinate exceeds 1024 bits",
        ));
    }
    q.to_f64().filter(|v| v.is_finite()).ok_or_else(|| {
        error(
            "tessellation_failed",
            "mesh",
            "Coordinate cannot be represented as float64",
        )
    })
}
pub fn evaluate(request: Request) -> Result<Mesh> {
    if !(16..=256).contains(&request.segments) {
        return Err(error(
            "mesh_limit",
            "segments",
            "Use 16..256 segments per circle",
        ));
    }
    let body = validate(&request.model)?
        .into_iter()
        .find(|b| b.feature_id == request.feature_id)
        .ok_or_else(|| {
            error(
                "missing_body",
                &request.feature_id,
                "Select a terminal solid",
            )
        })?;
    let names = if request.include_surfaces {
        Some(crate::topology::mesh_surfaces(&request.model, &body)?)
    } else {
        None
    };
    let build = |phase| -> Result<Mesh> {
        let mut mesh = build_mesh(&body, request.segments, phase, request.include_surfaces)?;
        if let (Some(surfaces), Some(names)) = (&mut mesh.triangle_surfaces, &names) {
            for role in surfaces {
                *role = names
                    .get(role)
                    .ok_or_else(|| {
                        error(
                            "tessellation_failed",
                            "mesh",
                            "Missing native surface provenance",
                        )
                    })?
                    .clone();
            }
        }
        Ok(mesh)
    };
    let first = build(0.0);
    if first.is_err()
        && body
            .analytic
            .as_ref()
            .is_some_and(|s| s.outer_circle.is_some())
    {
        // Aligned circular samples can make an earcut bridge triangle collinear.
        // Retry bounded sample phases of the same circles, never native geometry.
        // Every candidate still passes containment and complete mesh validation.
        for phase in [0.5, 0.25] {
            if let Ok(mesh) = build(phase) {
                return Ok(mesh);
            }
        }
    }
    first
}
fn build_mesh(body: &Body, segments: usize, phase: f64, tagged: bool) -> Result<Mesh> {
    let fail = || {
        error("tessellation_failed",&body.feature_id,"Float tessellation failed; exact model is unchanged. Change scale or spacing before exporting")
    };
    let mut mesh = Mesh {
        vertices: vec![],
        triangles: vec![],
        edges: vec![],
        max_radial_error_mm: 0.0,
        triangle_surfaces: tagged.then(Vec::new),
    };
    if let Some(b) = &body.boundary {
        for p in &b.vertices {
            mesh.vertices
                .push([value(&p[0])?, value(&p[1])?, value(&p[2])?]);
        }
        for (face_index, f) in b.faces.iter().enumerate() {
            let normal = [
                value(&f.normal[0])?,
                value(&f.normal[1])?,
                value(&f.normal[2])?,
            ];
            let axis = (0..3)
                .max_by(|&a, &b| normal[a].abs().total_cmp(&normal[b].abs()))
                .ok_or_else(fail)?;
            // Cyclic coordinates preserve the sign of the omitted normal axis.
            let u = (axis + 1) % 3;
            let v = (axis + 2) % 3;
            let mut ids = vec![];
            let mut holes = vec![];
            for (index, ring) in f.loops.iter().enumerate() {
                if index > 0 {
                    holes.push(ids.len());
                }
                ids.extend(
                    ring.iter()
                        .map(|edge| b.edges[edge.edge].vertices[usize::from(!edge.forward)]),
                );
            }
            let origin = mesh.vertices[ids[0]];
            let flat: Vec<_> = ids
                .iter()
                .flat_map(|&i| {
                    [
                        mesh.vertices[i][u] - origin[u],
                        mesh.vertices[i][v] - origin[v],
                    ]
                })
                .collect();
            let triangles = earcutr::earcut(&flat, &holes, 2).map_err(|_| fail())?;
            for t in triangles.chunks_exact(3) {
                let mut triangle = [ids[t[0]], ids[t[1]], ids[t[2]]];
                let [a, b, c] = triangle.map(|i| mesh.vertices[i]);
                let area = (b[u] - a[u]) * (c[v] - a[v]) - (b[v] - a[v]) * (c[u] - a[u]);
                if area * normal[axis] < 0.0 {
                    triangle.swap(1, 2);
                }
                mesh.triangle(triangle, &format!("evaluated/face/{face_index}"));
            }
        }
        mesh.edges = b.edges.iter().map(|e| e.vertices).collect();
    } else if let Some(profile) = body.analytic.as_ref().and_then(|s| s.revolution.as_ref()) {
        let mut rings = Vec::new();
        let mut radii = Vec::new();
        for p in &profile.points {
            let r = value(&p[0])?;
            let z = value(&p[1])?;
            radii.push(r);
            if r == 0.0 {
                let index = mesh.vertices.len();
                mesh.vertices.push([0.0, 0.0, z]);
                rings.push(vec![index; segments]);
            } else {
                let mut ring = Vec::new();
                for i in 0..segments {
                    let theta = std::f64::consts::TAU * (i as f64 + phase) / segments as f64;
                    ring.push(mesh.vertices.len());
                    mesh.vertices.push([r * theta.cos(), r * theta.sin(), z]);
                }
                for i in 0..segments {
                    mesh.edges.push([ring[i], ring[(i + 1) % segments]]);
                }
                rings.push(ring);
                mesh.max_radial_error_mm = mesh
                    .max_radial_error_mm
                    .max(r * (1.0 - (std::f64::consts::PI / segments as f64).cos()));
            }
        }
        for i in 0..rings.len() {
            let next = (i + 1) % rings.len();
            if radii[i] == 0.0 && radii[next] == 0.0 {
                continue;
            }
            for k in 0..segments {
                let j = (k + 1) % segments;
                for t in [
                    [rings[i][k], rings[i][j], rings[next][j]],
                    [rings[i][k], rings[next][j], rings[next][k]],
                ] {
                    if t[0] != t[1] && t[1] != t[2] && t[0] != t[2] {
                        mesh.triangle(t, &profile.roles[i]);
                    }
                }
                if radii[i] > 0.0
                    && radii[next] > 0.0
                    && profile.points[i][1] != profile.points[next][1]
                    && k % (segments / 4) == 0
                {
                    mesh.edges.push([rings[i][k], rings[next][k]]);
                }
            }
        }
    } else if body
        .analytic
        .as_ref()
        .is_some_and(|s| s.counterbore.is_some() || s.countersink.is_some())
    {
        mesh = crate::mesh_counterbore::build(body, segments, phase, tagged)?;
    } else if let Some(shape) = &body.analytic {
        let h = value(&shape.height)?;
        let mut points = Vec::new();
        for p in &shape.outer {
            points.push([value(&p[0])?, value(&p[1])?]);
        }
        if let Some(outer) = &shape.outer_circle {
            let (x, y, r) = (
                value(&outer.center[0])?,
                value(&outer.center[1])?,
                value(&outer.radius)?,
            );
            let inset = r * (std::f64::consts::PI / segments as f64).cos();
            mesh.max_radial_error_mm = r - inset;
            let epsilon = 64.0 * f64::EPSILON * x.abs().max(y.abs()).max(r).max(1.0);
            let mut accepted: Vec<(f64, f64, f64)> = vec![];
            for hole in &shape.holes {
                let (hx, hy, hr) = (
                    value(&hole.center[0])?,
                    value(&hole.center[1])?,
                    value(&hole.radius)?,
                );
                // Keep each complete hole disk inside the polygon's incircle.
                // A smaller exact gap may be valid natively but not at this chord count.
                if inset - (hx - x).hypot(hy - y) - hr <= epsilon {
                    return Err(fail());
                }
                if accepted
                    .iter()
                    .any(|(ax, ay, ar)| (hx - ax).hypot(hy - ay) - hr - ar <= epsilon)
                {
                    return Err(fail());
                }
                accepted.push((hx, hy, hr));
            }
            for i in 0..segments {
                let a = std::f64::consts::TAU * (i as f64 + phase) / segments as f64;
                points.push([x + r * a.cos(), y + r * a.sin()]);
            }
        }
        let mut starts = vec![0];
        for hole in &shape.holes {
            starts.push(points.len());
            let (x, y, r) = (
                value(&hole.center[0])?,
                value(&hole.center[1])?,
                value(&hole.radius)?,
            );
            mesh.max_radial_error_mm = mesh
                .max_radial_error_mm
                .max(r * (1.0 - (std::f64::consts::PI / segments as f64).cos()));
            for i in 0..segments {
                let a = -std::f64::consts::TAU * (i as f64 + phase) / segments as f64;
                points.push([x + r * a.cos(), y + r * a.sin()]);
            }
        }
        let flat: Vec<_> = points.iter().flatten().copied().collect();
        let cap = earcutr::earcut(&flat, &starts[1..], 2).map_err(|_| fail())?;
        let n = points.len();
        let outer_n = starts.get(1).copied().unwrap_or(n);
        let mut floors = vec![0.0; n];
        for (j, hole) in shape.holes.iter().enumerate() {
            if let Some(depth) = hole.depth.as_ref().or(shape.hole_depth.as_ref()) {
                let z = h - value(depth)?;
                if z <= 0.0 || z >= h {
                    return Err(fail());
                }
                let start = starts[j + 1];
                let end = starts.get(j + 2).copied().unwrap_or(n);
                floors[start..end].fill(z);
            }
        }
        mesh.vertices
            .extend(points.iter().zip(&floors).map(|(p, z)| [p[0], p[1], *z]));
        if let Some(top) = &shape.top_radius {
            let circle = shape.outer_circle.as_ref().ok_or_else(fail)?;
            let x = value(&circle.center[0])?;
            let y = value(&circle.center[1])?;
            let bottom = value(&circle.radius)?;
            let top = value(top)?;
            if top == bottom {
                return Err(fail());
            }
            mesh.vertices.extend(points.iter().map(|p| {
                [
                    x + (p[0] - x) * top / bottom,
                    y + (p[1] - y) * top / bottom,
                    h,
                ]
            }));
            mesh.max_radial_error_mm =
                bottom.max(top) * (1.0 - (std::f64::consts::PI / segments as f64).cos());
        } else {
            mesh.vertices.extend(points.iter().map(|p| [p[0], p[1], h]));
        }
        let orient = |t: &[usize]| {
            let (a, b, c) = (points[t[0]], points[t[1]], points[t[2]]);
            let mut ids = [t[0], t[1], t[2]];
            if (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]) < 0.0 {
                ids.swap(1, 2);
            }
            ids
        };
        for t in cap.chunks_exact(3) {
            let ids = orient(t);
            if shape.hole_depth.is_none() {
                mesh.triangle([ids[2], ids[1], ids[0]], "cap/bottom");
            }
            mesh.triangle(ids.map(|i| i + n), "cap/top");
        }
        if shape.hole_depth.is_some() {
            let bottom = earcutr::earcut(&flat[..outer_n * 2], &[], 2).map_err(|_| fail())?;
            for t in bottom.chunks_exact(3) {
                let ids = orient(t);
                mesh.triangle([ids[2], ids[1], ids[0]], "cap/bottom");
            }
            // Each clockwise hole ring closes with an upward-facing flat floor.
            for (j, &start) in starts.iter().enumerate().skip(1) {
                let end = starts.get(j + 1).copied().unwrap_or(n);
                for i in start + 1..end - 1 {
                    mesh.triangle(
                        [start, i + 1, i],
                        &format!("hole/{}/floor", shape.holes[j - 1].id),
                    );
                }
            }
        }
        starts.push(n);
        for (ring_index, ring) in starts.windows(2).enumerate() {
            for a in ring[0]..ring[1] {
                let b = if a + 1 == ring[1] { ring[0] } else { a + 1 };
                let role = if ring_index > 0 {
                    format!("hole/{}/wall", shape.holes[ring_index - 1].id)
                } else if shape.top_radius.is_some() {
                    "outer/frustum".into()
                } else if shape.outer_circle.is_some() {
                    "outer/cylinder".into()
                } else {
                    format!("outer/side/{a}")
                };
                mesh.triangle([a, b, b + n], &role);
                mesh.triangle([a, b + n, a + n], &role);
                mesh.edges.extend([[a, b], [a + n, b + n]]);
            }
        }
    }
    if let Some(placement) = body.analytic.as_ref().and_then(|s| s.placement.as_ref()) {
        let origin = [
            value(&placement.origin[0])?,
            value(&placement.origin[1])?,
            value(&placement.origin[2])?,
        ];
        for point in &mut mesh.vertices {
            *point = std::array::from_fn(|row| {
                origin[row]
                    + (0..3)
                        .map(|col| f64::from(placement.axes[row][col]) * point[col])
                        .sum::<f64>()
            });
        }
    }
    // Refuse collapsed triangles or missing/misoriented edge incidence, including
    // earcut's possible removal of numerically indistinguishable ring vertices.
    let mut incidence: BTreeMap<[usize; 2], Vec<bool>> = BTreeMap::new();
    for t in &mesh.triangles {
        let [a, b, c] = t.map(|i| mesh.vertices[i]);
        let u = [b[0] - a[0], b[1] - a[1], b[2] - a[2]];
        let v = [c[0] - a[0], c[1] - a[1], c[2] - a[2]];
        let normal = [
            u[1] * v[2] - u[2] * v[1],
            u[2] * v[0] - u[0] * v[2],
            u[0] * v[1] - u[1] * v[0],
        ];
        if !normal.iter().all(|n| n.is_finite()) || normal.iter().all(|n| *n == 0.0) {
            return Err(fail());
        }
        for i in 0..3 {
            let (a, b) = (t[i], t[(i + 1) % 3]);
            incidence
                .entry([a.min(b), a.max(b)])
                .or_default()
                .push(a < b);
        }
    }
    if incidence.is_empty() || incidence.values().any(|v| v.len() != 2 || v[0] == v[1]) {
        return Err(fail());
    }
    Ok(mesh)
}
