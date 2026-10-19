//! Display-only rings for exact stepped cylindrical holes.
use crate::{
    error,
    mesh::{value, Mesh},
    Body, Result,
};
fn ring(
    center: [f64; 2],
    radius: f64,
    z: f64,
    segments: usize,
    phase: f64,
    direction: f64,
) -> Vec<[f64; 3]> {
    (0..segments)
        .map(|i| {
            let a = direction * std::f64::consts::TAU * (i as f64 + phase) / segments as f64;
            [
                center[0] + radius * a.cos(),
                center[1] + radius * a.sin(),
                z,
            ]
        })
        .collect()
}
fn wall(mesh: &mut Mesh, bottom: usize, top: usize, count: usize, role: &str) {
    for i in 0..count {
        let j = (i + 1) % count;
        let surface = if role == "outer/side" {
            format!("{role}/{i}")
        } else {
            role.into()
        };
        mesh.triangle([bottom + i, bottom + j, top + j], &surface);
        mesh.triangle([bottom + i, top + j, top + i], &surface);
        mesh.edges
            .extend([[bottom + i, bottom + j], [top + i, top + j]]);
    }
}
pub(super) fn build(body: &Body, segments: usize, phase: f64, tagged: bool) -> Result<Mesh> {
    let fail = || {
        error("tessellation_failed",&body.feature_id,"Counterbore cannot be resolved at this display scale or chord count; exact model is unchanged")
    };
    let shape = body.analytic.as_ref().unwrap();
    let bore = shape.counterbore.as_ref().unwrap();
    let h = value(&shape.height)?;
    let depth = value(&bore.depth)?;
    let floor = h - depth;
    let radius = value(&bore.radius)?;
    if floor <= 0.0 || floor >= h {
        return Err(fail());
    }
    let mut outer = shape
        .outer
        .iter()
        .map(|p| Ok([value(&p[0])?, value(&p[1])?, 0.0]))
        .collect::<Result<Vec<_>>>()?;
    let mut error_radius = radius;
    let round = shape
        .outer_circle
        .as_ref()
        .map(|c| {
            Ok((
                value(&c.center[0])?,
                value(&c.center[1])?,
                value(&c.radius)?,
            ))
        })
        .transpose()?;
    if let Some((x, y, r)) = round {
        outer = ring([x, y], r, 0.0, segments, phase, 1.0);
        error_radius = error_radius.max(r);
    }
    let outer_n = outer.len();
    let mut bottom = outer.clone();
    let mut top: Vec<_> = outer.iter().map(|p| [p[0], p[1], h]).collect();
    let mut holes = vec![];
    let mut disks: Vec<(f64, f64, f64)> = vec![];
    for hole in &shape.holes {
        let (x, y, r) = (
            value(&hole.center[0])?,
            value(&hole.center[1])?,
            value(&hole.radius)?,
        );
        let eps = 64.0 * f64::EPSILON * x.abs().max(y.abs()).max(radius).max(h).max(1.0);
        if radius - r <= eps || floor <= eps || depth <= eps {
            return Err(fail());
        }
        if let Some((ox, oy, or)) = round {
            if or * (std::f64::consts::PI / segments as f64).cos() - (x - ox).hypot(y - oy) - radius
                <= eps
            {
                return Err(fail());
            }
        }
        if disks
            .iter()
            .any(|(a, b, _)| (x - a).hypot(y - b) - 2.0 * radius <= eps)
        {
            return Err(fail());
        }
        holes.push(bottom.len());
        bottom.extend(ring([x, y], r, 0.0, segments, phase, -1.0));
        top.extend(ring([x, y], radius, h, segments, phase, -1.0));
        disks.push((x, y, r));
    }
    let n = bottom.len();
    let mut mesh = Mesh {
        vertices: bottom,
        triangles: vec![],
        triangle_surfaces: tagged.then(Vec::new),
        edges: vec![],
        max_radial_error_mm: error_radius * (1.0 - (std::f64::consts::PI / segments as f64).cos()),
    };
    mesh.vertices.extend(top);
    for side in 0..2 {
        let offset = side * n;
        let points = &mesh.vertices[offset..offset + n];
        let origin = points[0];
        let flat: Vec<_> = points
            .iter()
            .flat_map(|p| [p[0] - origin[0], p[1] - origin[1]])
            .collect();
        let cap = earcutr::earcut(&flat, &holes, 2).map_err(|_| fail())?;
        for t in cap.chunks_exact(3) {
            let [a, b, c] = [points[t[0]], points[t[1]], points[t[2]]];
            let mut ids = [t[0] + offset, t[1] + offset, t[2] + offset];
            let area = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]);
            if (area < 0.0) == (side == 1) {
                ids.swap(1, 2);
            }
            mesh.triangles.push(ids);
            if let Some(surfaces) = &mut mesh.triangle_surfaces {
                surfaces.push(if side == 0 { "cap/bottom" } else { "cap/top" }.into());
            }
        }
    }
    wall(
        &mut mesh,
        0,
        n,
        outer_n,
        if round.is_some() {
            "outer/cylinder"
        } else {
            "outer/side"
        },
    );
    for (j, (x, y, r)) in disks.into_iter().enumerate() {
        let large = mesh.vertices.len();
        mesh.vertices
            .extend(ring([x, y], radius, floor, segments, phase, -1.0));
        let small = mesh.vertices.len();
        mesh.vertices
            .extend(ring([x, y], r, floor, segments, phase, -1.0));
        let role = format!("hole/{}", shape.holes[j].id);
        wall(
            &mut mesh,
            holes[j],
            small,
            segments,
            &format!("{role}/lower"),
        );
        wall(
            &mut mesh,
            large,
            n + holes[j],
            segments,
            &format!("{role}/upper"),
        );
        for i in 0..segments {
            let next = (i + 1) % segments;
            let shoulder = format!("{role}/shoulder");
            mesh.triangle([large + i, small + i, small + next], &shoulder);
            mesh.triangle([large + i, small + next, large + next], &shoulder);
        }
    }
    Ok(mesh)
}
