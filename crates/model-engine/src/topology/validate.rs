//! Exact support/incidence checks for the bounded internally constructed boundary.
use super::*;
use num_traits::Signed;
use std::collections::{BTreeMap, BTreeSet};
use std::sync::OnceLock;
type Audit = (Vec<Vec<usize>>, Vec<i32>);
fn atan_bounds(x: i32, n: usize) -> (Q, Q) {
    let x = Q::from_integer(x.into());
    let square = &x * &x;
    let mut power = x;
    let mut sum = q(0);
    for k in 0..n {
        let term = q(1) / (q((2 * k + 1) as i32) * &power);
        if k % 2 == 0 {
            sum += term;
        } else {
            sum -= term;
        }
        power *= &square;
    }
    let next = q(1) / (q((2 * n + 1) as i32) * power);
    if n % 2 == 0 {
        (sum.clone(), sum + next)
    } else {
        (sum.clone() - next, sum)
    }
}
fn pi_bounds(n: usize) -> (Q, Q) {
    let (a, b) = atan_bounds(5, n);
    let (c, d) = atan_bounds(239, n);
    (q(16) * a - q(4) * d, q(16) * b - q(4) * c)
}
fn sign(a: &Q, b: &Q) -> Result<i32> {
    if b.is_zero() {
        return Ok(if a.is_positive() {
            1
        } else if a.is_negative() {
            -1
        } else {
            0
        });
    }
    if a.is_zero() || a.is_positive() == b.is_positive() {
        return Ok(if b.is_positive() { 1 } else { -1 });
    }
    static PI: OnceLock<(Q, Q)> = OnceLock::new();
    for n in [32, 128, 512] {
        let computed;
        let (lo, hi) = if n == 32 {
            PI.get_or_init(|| pi_bounds(32))
        } else {
            computed = pi_bounds(n);
            &computed
        };
        let first = a + b * lo;
        let last = a + b * hi;
        if first.is_positive() && last.is_positive() {
            return Ok(1);
        }
        if first.is_negative() && last.is_negative() {
            return Ok(-1);
        }
    }
    Err(error(
        "topology_limit",
        "boundary",
        "Plane-loop orientation exceeds certified pi interval budget",
    ))
}
fn on_surface(surface: &Surface, edge: &Edge, points: &[Point]) -> Result<()> {
    let a = &points[edge.vertices[0]];
    let b = &points[edge.vertices[1]];
    match surface {
        Surface::Plane { normal, offset } => {
            let normal = point(normal)?;
            let offset = value(offset)?;
            if is_zero(&normal) || dot(&normal, a) != offset || dot(&normal, b) != offset {
                return Err(fail("Edge endpoint off plane"));
            }
            if let Curve::QuarterCircle {
                center,
                axis: direction,
                ..
            } = &edge.curve
            {
                if !is_zero(&cross(&normal, &axis(*direction)?))
                    || dot(&normal, &point(center)?) != offset
                {
                    return Err(fail("Arc support off plane"));
                }
            }
        }
        Surface::ConicalFrustum {
            origin,
            axis: direction,
            bottom_radius,
            top_radius,
            height,
        } => {
            let origin = point(origin)?;
            let direction = axis(*direction)?;
            let r0 = value(bottom_radius)?;
            let r1 = value(top_radius)?;
            let h = value(height)?;
            if !r0.is_positive() || !r1.is_positive() || !h.is_positive() || r0 == r1 {
                return Err(fail("Invalid conical frustum dimensions"));
            }
            let radial = |p: &Point| {
                let d = sub(p, &origin);
                let z = dot(&d, &direction);
                let radial: Point = std::array::from_fn(|i| &d[i] - &direction[i] * &z);
                let r = &r0 + (&r1 - &r0) * &z / &h;
                (radial, z, r)
            };
            let (ra, za, a_radius) = radial(a);
            let (rb, zb, b_radius) = radial(b);
            for (r, z, radius) in [(&ra, &za, &a_radius), (&rb, &zb, &b_radius)] {
                if z < &q(0) || z > &h || dot(r, r) != radius * radius {
                    return Err(fail("Edge endpoint off bounded conical surface"));
                }
            }
            match &edge.curve {
                Curve::Line => {
                    if za == zb || (0..3).any(|i| &ra[i] * &b_radius != &rb[i] * &a_radius) {
                        return Err(fail("Conical edge is not a generator"));
                    }
                }
                Curve::QuarterCircle {
                    center,
                    axis: arc_axis,
                    radius,
                } => {
                    if za != zb
                        || value(radius)? != a_radius
                        || !is_zero(&radial(&point(center)?).0)
                        || dot(&sub(&point(center)?, &origin), &direction) != za
                        || !is_zero(&cross(&direction, &axis(*arc_axis)?))
                    {
                        return Err(fail("Arc support off conical surface"));
                    }
                }
            }
        }
        Surface::Cylinder {
            origin,
            axis: direction,
            radius,
            ..
        } => {
            let origin = point(origin)?;
            let direction = axis(*direction)?;
            let radius = value(radius)?;
            if !radius.is_positive() {
                return Err(fail("Nonpositive cylinder radius"));
            }
            let radial = |p: &Point| {
                let d = sub(p, &origin);
                let axial = dot(&d, &direction);
                std::array::from_fn(|i| &d[i] - &direction[i] * &axial)
            };
            let ra: Point = radial(a);
            let rb: Point = radial(b);
            if dot(&ra, &ra) != &radius * &radius || dot(&rb, &rb) != &radius * &radius {
                return Err(fail("Edge endpoint off cylinder"));
            }
            match &edge.curve {
                Curve::Line => {
                    if ra != rb {
                        return Err(fail("Nonaxial cylinder line"));
                    }
                }
                Curve::QuarterCircle {
                    center,
                    axis: arc_axis,
                    radius: arc_radius,
                } => {
                    if value(arc_radius)? != radius
                        || !is_zero(&cross(&direction, &axis(*arc_axis)?))
                        || !is_zero(&radial(&point(center)?))
                    {
                        return Err(fail("Arc support off cylinder"));
                    }
                }
            }
        }
    }
    Ok(())
}
fn orientation(
    surface: &Surface,
    ring: &[Use],
    index: usize,
    topology: &Topology,
    points: &[Point],
) -> Result<()> {
    match surface {
        Surface::Plane { normal, .. } => {
            let mut constant: Point = std::array::from_fn(|_| q(0));
            let mut pi: Point = std::array::from_fn(|_| q(0));
            for u in ring {
                let edge = &topology.edges[u.edge];
                let [a, b] = edge.vertices;
                let oriented = if u.forward { q(1) } else { q(-1) };
                let chord = cross(&points[a], &points[b]);
                for i in 0..3 {
                    constant[i] += &oriented * &chord[i];
                }
                if let Curve::QuarterCircle {
                    axis: direction,
                    radius,
                    ..
                } = &edge.curve
                {
                    let direction = axis(*direction)?;
                    let r = value(radius)?;
                    for i in 0..3 {
                        let area = &oriented * &direction[i] * &r * &r;
                        constant[i] -= &area;
                        pi[i] += area / q(2);
                    }
                }
            }
            let normal = point(normal)?;
            if sign(&dot(&normal, &constant), &dot(&normal, &pi))?
                != if index == 0 { 1 } else { -1 }
            {
                return Err(fail("Incorrect plane-loop orientation"));
            }
        }
        Surface::Cylinder {
            axis: direction, ..
        }
        | Surface::ConicalFrustum {
            axis: direction, ..
        } => {
            let inward = matches!(surface, Surface::Cylinder { inward: true, .. });
            if index != 0 || ring.len() != 4 {
                return Err(fail("Round wall patches require one four-edge loop"));
            }
            let direction = axis(*direction)?;
            let mut arcs = vec![];
            for u in ring {
                if let Curve::QuarterCircle {
                    center,
                    axis: arc_axis,
                    ..
                } = &topology.edges[u.edge].curve
                {
                    arcs.push((
                        dot(&point(center)?, &direction),
                        dot(&axis(*arc_axis)?, &direction) * q(if u.forward { 1 } else { -1 }),
                    ));
                }
            }
            arcs.sort();
            let expected = q(if inward { -1 } else { 1 });
            if arcs.len() != 2
                || arcs[0].0 >= arcs[1].0
                || arcs[0].1 != expected
                || arcs[1].1 != -expected
            {
                return Err(fail("Incorrect round wall patch orientation"));
            }
        }
    }
    Ok(())
}
fn connected(graph: &BTreeMap<usize, Vec<usize>>) -> BTreeSet<usize> {
    let mut found = BTreeSet::new();
    let mut stack: Vec<_> = graph.keys().take(1).copied().collect();
    while let Some(i) = stack.pop() {
        if found.insert(i) {
            stack.extend(&graph[&i]);
        }
    }
    found
}
pub(super) fn check(t: &Topology) -> Result<Audit> {
    if t.vertices.is_empty()
        || t.vertices.len() > 1024
        || t.edges.is_empty()
        || t.edges.len() > 2048
        || t.faces.is_empty()
        || t.faces.len() > 1024
        || t.surfaces.len() > 1024
    {
        return Err(error(
            "topology_limit",
            "boundary",
            "Boundary count budget exceeded",
        ));
    }
    let points = t.vertices.iter().map(point).collect::<Result<Vec<_>>>()?;
    if points.iter().collect::<BTreeSet<_>>().len() != points.len() {
        return Err(fail("Duplicate vertex coordinates"));
    }
    let mut used_vertices = BTreeSet::new();
    for edge in &t.edges {
        let [a, b] = edge.vertices;
        if a >= points.len() || b >= points.len() || a == b {
            return Err(fail("Invalid or degenerate edge endpoints"));
        }
        used_vertices.extend([a, b]);
        if let Curve::QuarterCircle {
            center,
            axis: direction,
            radius,
        } = &edge.curve
        {
            let center = point(center)?;
            let direction = axis(*direction)?;
            let r = value(radius)?;
            let a = sub(&points[a], &center);
            let b = sub(&points[b], &center);
            let square = &r * &r;
            if !r.is_positive()
                || dot(&a, &a) != square
                || dot(&b, &b) != square
                || !dot(&a, &direction).is_zero()
                || !dot(&b, &direction).is_zero()
                || !dot(&a, &b).is_zero()
                || cross(&a, &b) != direction.map(|v| v * &square)
            {
                return Err(fail("Invalid exact quarter-circle endpoints"));
            }
        }
    }
    if used_vertices.len() != points.len() {
        return Err(fail("Unused vertex"));
    }
    let mut owners = vec![vec![]; t.edges.len()];
    let mut face_ids = BTreeSet::new();
    let mut surfaces = BTreeSet::new();
    for (i, face) in t.faces.iter().enumerate() {
        if !face_ids.insert(&face.id) {
            return Err(fail("Duplicate face ID"));
        }
        let record = t
            .surfaces
            .get(&face.surface)
            .ok_or_else(|| fail("Missing surface"))?;
        surfaces.insert(&face.surface);
        if face.loops.is_empty() {
            return Err(fail("Missing face loop"));
        }
        let mut seen = BTreeSet::new();
        for (loop_index, ring) in face.loops.iter().enumerate() {
            if ring.len() < 3 || ring.len() > 2048 {
                return Err(fail("Invalid face-loop size"));
            }
            for (j, u) in ring.iter().enumerate() {
                if u.edge >= t.edges.len() || ring[(j + 1) % ring.len()].edge >= t.edges.len() {
                    return Err(fail("Missing edge reference"));
                }
                let edge = &t.edges[u.edge];
                let next = &ring[(j + 1) % ring.len()];
                let start = edge.vertices[usize::from(!u.forward)];
                let end = edge.vertices[usize::from(u.forward)];
                if end != t.edges[next.edge].vertices[usize::from(!next.forward)]
                    || !seen.insert(start)
                {
                    return Err(fail("Open loop or repeated face vertex"));
                }
                on_surface(&record.geometry, edge, &points)?;
                owners[u.edge].push((i, u.forward));
            }
            orientation(&record.geometry, ring, loop_index, t, &points)?;
        }
    }
    if surfaces.len() != t.surfaces.len() {
        return Err(fail("Unused surface"));
    }
    let mut graph: BTreeMap<usize, Vec<usize>> = (0..t.faces.len()).map(|i| (i, vec![])).collect();
    let mut links: Vec<BTreeMap<usize, Vec<usize>>> = vec![BTreeMap::new(); points.len()];
    for (edge, uses) in t.edges.iter().zip(owners) {
        if uses.len() != 2 || uses[0].0 == uses[1].0 || uses[0].1 == uses[1].1 {
            return Err(fail("Open, nonmanifold or inconsistently oriented edge"));
        }
        let (a, b) = (uses[0].0, uses[1].0);
        graph.get_mut(&a).unwrap().push(b);
        graph.get_mut(&b).unwrap().push(a);
        for v in edge.vertices {
            links[v].entry(a).or_default().push(b);
            links[v].entry(b).or_default().push(a);
        }
    }
    for link in links {
        if link.values().any(|adj| adj.len() != 2) || connected(&link).len() != link.len() {
            return Err(fail("Vertex link is not one closed cycle"));
        }
    }
    let mut shells = vec![];
    let mut eulers = vec![];
    while !graph.is_empty() {
        let found = connected(&graph);
        let edges: BTreeSet<_> = found
            .iter()
            .flat_map(|&i| t.faces[i].loops.iter().flatten().map(|u| u.edge))
            .collect();
        let vertices: BTreeSet<_> = edges.iter().flat_map(|&i| t.edges[i].vertices).collect();
        let euler = vertices.len() as i32 - edges.len() as i32
            + found
                .iter()
                .map(|&i| 2 - t.faces[i].loops.len() as i32)
                .sum::<i32>();
        if euler > 2 || euler % 2 != 0 {
            return Err(fail("Invalid closed-shell Euler characteristic"));
        }
        for i in &found {
            graph.remove(i);
        }
        shells.push(found.into_iter().collect::<Vec<_>>());
        eulers.push(euler);
    }
    let mut components = BTreeMap::new();
    for (group, faces) in t.components.iter().enumerate() {
        if faces.is_empty() {
            return Err(fail("Empty material component"));
        }
        for &face in faces {
            if face >= t.faces.len() || components.insert(face, group).is_some() {
                return Err(fail("Invalid component membership"));
            }
        }
    }
    if components.len() != t.faces.len()
        || shells.iter().any(|s| {
            s.iter()
                .map(|f| components[f])
                .collect::<BTreeSet<_>>()
                .len()
                != 1
        })
    {
        return Err(fail("Component membership splits or omits a shell"));
    }
    Ok((shells, eulers))
}

#[cfg(test)]
mod interval_tests {
    use super::*;
    #[test]
    fn certified_pi_bounds_and_adaptive_sign() {
        // Alternating-series enclosures nest, and lie between familiar rationals.
        let (lo, hi) = pi_bounds(32);
        let (fine_lo, fine_hi) = pi_bounds(128);
        assert!(q(333) / q(106) < lo && hi < q(355) / q(113));
        assert!(lo < fine_lo && fine_hi < hi);
        assert_eq!(sign(&q(0), &q(0)).unwrap(), 0);
        assert_eq!(sign(&q(0), &q(-1)).unwrap(), -1);
        assert_eq!(sign(&(-lo.clone()), &q(1)).unwrap(), 1);
        assert_eq!(sign(&(-hi.clone()), &q(1)).unwrap(), -1);
        // These require the second interval; reversing both coefficients reverses sign.
        let near = (lo + hi) / q(2);
        let expected = if near < fine_lo { 1 } else { -1 };
        assert!(near < fine_lo || near > fine_hi);
        assert_eq!(sign(&(-near.clone()), &q(1)).unwrap(), expected);
        assert_eq!(sign(&near, &q(-1)).unwrap(), -expected);
        // tan(4 atan(1/5) - atan(1/239)) = 1, with angle in (0, pi/2).
        let double = |t: Q| q(2) * &t / (q(1) - &t * &t);
        let a = double(double(q(1) / q(5)));
        let b = q(1) / q(239);
        assert_eq!((&a - &b) / (q(1) + a * b), q(1));
    }
}
