//! Disposable float64 tessellation. Failure never invalidates an exact saved model.
use crate::{error, rational, validate, Body, Model, Result};
use num_traits::ToPrimitive;
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Request {
    pub model: Model,
    pub feature_id: String,
    pub segments: usize,
}
#[derive(Serialize)]
pub struct Mesh {
    pub vertices: Vec<[f64; 3]>,
    pub triangles: Vec<[usize; 3]>,
    pub edges: Vec<[usize; 2]>,
    pub max_radial_error_mm: f64,
}
fn value(s: &str) -> Result<f64> {
    rational(s, "mesh")?
        .to_f64()
        .filter(|v| v.is_finite())
        .ok_or_else(|| {
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
    let first = build_mesh(&body, request.segments, 0.0);
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
            if let Ok(mesh) = build_mesh(&body, request.segments, phase) {
                return Ok(mesh);
            }
        }
    }
    first
}
fn build_mesh(body: &Body, segments: usize, phase: f64) -> Result<Mesh> {
    let fail = || {
        error("tessellation_failed",&body.feature_id,"Float tessellation failed; exact model is unchanged. Change scale or spacing before exporting")
    };
    let mut mesh = Mesh {
        vertices: vec![],
        triangles: vec![],
        edges: vec![],
        max_radial_error_mm: 0.0,
    };
    if let Some(b) = &body.boundary {
        for p in &b.vertices {
            mesh.vertices
                .push([value(&p[0])?, value(&p[1])?, value(&p[2])?]);
        }
        for f in &b.faces {
            let ids: Vec<_> = f.loops[0]
                .iter()
                .map(|u| b.edges[u.edge].vertices[usize::from(!u.forward)])
                .collect();
            for i in 1..ids.len() - 1 {
                mesh.triangles.push([ids[0], ids[i], ids[i + 1]]);
            }
        }
        mesh.edges = b.edges.iter().map(|e| e.vertices).collect();
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
        let floor = if let Some(depth) = &shape.hole_depth {
            let z = h - value(depth)?;
            if z <= 0.0 || z >= h {
                return Err(fail());
            }
            z
        } else {
            0.0
        };
        mesh.vertices.extend(
            points
                .iter()
                .enumerate()
                .map(|(i, p)| [p[0], p[1], if i < outer_n { 0.0 } else { floor }]),
        );
        mesh.vertices.extend(points.iter().map(|p| [p[0], p[1], h]));
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
                mesh.triangles.push([ids[2], ids[1], ids[0]]);
            }
            mesh.triangles.push(ids.map(|i| i + n));
        }
        if shape.hole_depth.is_some() {
            let bottom = earcutr::earcut(&flat[..outer_n * 2], &[], 2).map_err(|_| fail())?;
            for t in bottom.chunks_exact(3) {
                let ids = orient(t);
                mesh.triangles.push([ids[2], ids[1], ids[0]]);
            }
            // Each clockwise hole ring closes with an upward-facing flat floor.
            for (j, &start) in starts.iter().enumerate().skip(1) {
                let end = starts.get(j + 1).copied().unwrap_or(n);
                for i in start + 1..end - 1 {
                    mesh.triangles.push([start, i + 1, i]);
                }
            }
        }
        starts.push(n);
        for ring in starts.windows(2) {
            for a in ring[0]..ring[1] {
                let b = if a + 1 == ring[1] { ring[0] } else { a + 1 };
                mesh.triangles.extend([[a, b, b + n], [a, b + n, a + n]]);
                mesh.edges.extend([[a, b], [a + n, b + n]]);
            }
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
