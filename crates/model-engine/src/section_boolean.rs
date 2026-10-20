//! Exact Boolean boundaries of two simple, counterclockwise radial sections.
//! Split at every crossing/overlap endpoint; classify the open sides of each
//! atomic segment symbolically. No offset epsilon, sampling mesh or 3D cells.
use crate::{error, polyhedral::Operation, Result, Q};
use num_traits::{Signed, Zero};
use std::collections::{BTreeMap, BTreeSet};
type Point = [Q; 2];
type Segment = (Point, Point);
fn q(n: i32) -> Q {
    Q::from_integer(n.into())
}
fn cross(a: &Point, b: &Point, p: &Point) -> Q {
    (&b[0] - &a[0]) * (&p[1] - &a[1]) - (&b[1] - &a[1]) * (&p[0] - &a[0])
}
fn on_segment(p: &Point, a: &Point, b: &Point) -> bool {
    cross(a, b, p).is_zero()
        && (0..2).all(|i| &p[i] >= (&a[i]).min(&b[i]) && &p[i] <= (&a[i]).max(&b[i]))
}
fn edges(points: &[Point]) -> impl Iterator<Item = (&Point, &Point)> {
    points
        .iter()
        .zip(points.iter().cycle().skip(1))
        .take(points.len())
}
fn budget(p: &Point, id: &str) -> Result<()> {
    if p.iter()
        .any(|v| v.numer().bits() > 1024 || v.denom().bits() > 1024)
    {
        return Err(error(
            "polyhedral_limit",
            id,
            "Computed radial coordinate exceeds 1024 bits",
        ));
    }
    Ok(())
}
// Midpoints cannot be crossing points after splitting. At a coincident edge,
// use its exact direction to decide which open side contains material.
fn sides(a: &Point, b: &Point, poly: &[Point]) -> (bool, bool) {
    let p: Point = std::array::from_fn(|i| (&a[i] + &b[i]) / q(2));
    let mut winding = 0;
    for (u, v) in edges(poly) {
        let turn = cross(u, v, &p);
        if turn.is_zero() && on_segment(&p, u, v) {
            let axis = usize::from(a[0] == b[0]);
            let same = (b[axis] > a[axis]) == (v[axis] > u[axis]);
            return (same, !same);
        }
        if u[1] <= p[1] && v[1] > p[1] && turn.is_positive() {
            winding += 1;
        } else if u[1] > p[1] && v[1] <= p[1] && turn.is_negative() {
            winding -= 1;
        }
    }
    (winding != 0, winding != 0)
}
fn material(a: bool, b: bool, op: Operation) -> bool {
    match op {
        Operation::Union => a || b,
        Operation::Difference => a && !b,
        Operation::Intersection => a && b,
    }
}

pub(crate) fn combine(id: &str, a: &[Point], b: &[Point], op: Operation) -> Result<Vec<Point>> {
    // Inputs come from already validated, normalized sections (at most 32 edges).
    for point in a.iter().chain(b) {
        budget(point, id)?;
    }
    let source: Vec<_> = edges(a).chain(edges(b)).collect();
    let mut splits: Vec<BTreeSet<Point>> = source
        .iter()
        .map(|(u, v)| BTreeSet::from([(*u).clone(), (*v).clone()]))
        .collect();
    for (i, (u, v)) in source.iter().enumerate() {
        for (j, (p, r)) in source.iter().enumerate().skip(i + 1) {
            let before = cross(p, r, u);
            let after = cross(p, r, v);
            let denominator = &before - &after;
            if !denominator.is_zero() {
                let t = &before / denominator;
                if t >= q(0) && t <= q(1) {
                    let hit: Point = std::array::from_fn(|k| &u[k] + &t * (&v[k] - &u[k]));
                    if on_segment(&hit, p, r) {
                        budget(&hit, id)?;
                        splits[i].insert(hit.clone());
                        splits[j].insert(hit);
                    }
                }
            } else if before.is_zero() {
                for point in [*u, *v, *p, *r] {
                    if on_segment(point, u, v) && on_segment(point, p, r) {
                        splits[i].insert(point.clone());
                        splits[j].insert(point.clone());
                    }
                }
            }
        }
    }
    let mut atomic: BTreeSet<Segment> = BTreeSet::new();
    for split in splits {
        // Lexicographic order is monotone along any nonzero line segment.
        let points: Vec<_> = split.into_iter().collect();
        atomic.extend(points.windows(2).map(|w| (w[0].clone(), w[1].clone())));
    }
    if atomic.len() > 4096 {
        return Err(error(
            "polyhedral_limit",
            id,
            "Maximum 4096 radial segment pieces",
        ));
    }
    let mut boundary = BTreeSet::new();
    for (u, v) in atomic {
        let (al, ar) = sides(&u, &v, a);
        let (bl, br) = sides(&u, &v, b);
        let (left, right) = (material(al, bl, op), material(ar, br, op));
        if left != right {
            boundary.insert(if left { (u, v) } else { (v, u) });
        }
    }
    if boundary.is_empty() {
        return Err(error(
            "empty_solid",
            id,
            "Coaxial operation leaves no positive volume",
        ));
    }
    let invalid = || {
        error(
            "invalid_polyhedron",
            id,
            "Nonmanifold or touching radial boundary",
        )
    };
    let mut next = BTreeMap::new();
    let mut incoming = BTreeSet::new();
    for (u, v) in &boundary {
        if next.insert(u.clone(), v.clone()).is_some() || !incoming.insert(v.clone()) {
            return Err(invalid());
        }
    }
    if next.keys().cloned().collect::<BTreeSet<_>>() != incoming {
        return Err(invalid());
    }
    let start = next.keys().next().unwrap().clone();
    let mut p = start.clone();
    let mut points = Vec::new();
    loop {
        points.push(p.clone());
        let end = next[&p].clone();
        if !boundary.remove(&(p, end.clone())) {
            return Err(invalid());
        }
        p = end;
        if p == start {
            break;
        }
    }
    if !boundary.is_empty() {
        return Err(error(
            "unsupported_coaxial_result",
            id,
            "The result needs one connected radial region without interior contour holes",
        ));
    }
    // The former unit-prism bottom loop began at the least point clockwise,
    // then reversed. Retain that start convention for revision-only surface IDs.
    points.rotate_left(1);
    Ok(points)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{polyhedral::Solid, profile};

    fn polygon(points: &[(i32, i32)]) -> Vec<Point> {
        points.iter().map(|&(x, y)| [q(x), q(y)]).collect()
    }
    // Independent legacy path: 3D convex-cell splitting and merged planar faces.
    fn legacy(a: &[Point], b: &[Point], op: Operation) -> Result<Vec<Point>> {
        let solid = |points: &[Point]| {
            let p = profile::computed_polygon("test", points.to_vec())?;
            if profile::is_convex(&p) {
                Solid::from_convex(profile::extrude(&p, &q(1)))
            } else {
                Solid::from_profile(&p, &q(1))
            }
        };
        let s = solid(a)?.combine(&solid(b)?, op)?;
        let bottoms: Vec<_> = s
            .boundary
            .faces
            .iter()
            .filter(|f| {
                f.normal[0] == "0"
                    && f.normal[1] == "0"
                    && f.normal[2].starts_with('-')
                    && f.offset == "0"
            })
            .collect();
        if s.components.len() != 1 || bottoms.len() != 1 || bottoms[0].loops.len() != 1 {
            return Err(error(
                "unsupported_coaxial_result",
                "test",
                "Multiple regions or contour holes",
            ));
        }
        let mut points: Vec<Point> = bottoms[0].loops[0]
            .iter()
            .map(|u| {
                let edge = &s.boundary.edges[u.edge];
                let v = &s.boundary.vertices[edge.vertices[usize::from(!u.forward)]];
                [
                    crate::topology::value(&v[0]).unwrap(),
                    crate::topology::value(&v[1]).unwrap(),
                ]
            })
            .collect();
        points.reverse();
        Ok(points)
    }
    fn canonical(mut points: Vec<Point>) -> BTreeSet<Segment> {
        loop {
            let n = points.len();
            let index = (0..n).find(|&i| {
                cross(&points[(i + n - 1) % n], &points[i], &points[(i + 1) % n]).is_zero()
            });
            if let Some(i) = index {
                points.remove(i);
            } else {
                break;
            }
        }
        edges(&points)
            .map(|(u, v)| (u.clone(), v.clone()))
            .collect()
    }
    #[test]
    fn agrees_with_independent_cell_boundaries_on_crossings_overlaps_and_contacts() {
        let shapes = [
            polygon(&[(0, 0), (4, 0), (4, 5), (0, 5)]),
            polygon(&[(0, 0), (5, 0), (5, 2), (2, 2), (2, 5), (0, 5)]),
            polygon(&[(0, 0), (4, 1), (3, 5), (1, 4)]),
        ];
        let mut count = 0;
        for a in &shapes {
            for b in &shapes {
                for (dx, dy) in [(0, 0), (1, 1), (4, 0), (5, 5), (-1, 2)] {
                    let shifted: Vec<Point> = b
                        .iter()
                        .map(|p| [(&p[0] + q(dx)) / q(7), (&p[1] + q(dy)) / q(7)])
                        .collect();
                    let scaled: Vec<Point> =
                        a.iter().map(|p| [&p[0] / q(7), &p[1] / q(7)]).collect();
                    for op in [
                        Operation::Union,
                        Operation::Difference,
                        Operation::Intersection,
                    ] {
                        let old = legacy(&scaled, &shifted, op);
                        let new = combine("test", &scaled, &shifted, op);
                        match (old, new) {
                            (Ok(old), Ok(new)) => {
                                assert_eq!(canonical(old), canonical(new), "case {count} {op:?}")
                            }
                            (Err(old), Err(new)) => {
                                assert_eq!(old.code, new.code, "case {count} {op:?}")
                            }
                            (old, new) => {
                                panic!("case {count} {op:?}: legacy={old:?}, direct={new:?}")
                            }
                        }
                        count += 1;
                    }
                }
            }
        }
        assert_eq!(count, 135);
    }
    #[test]
    fn rejects_holes_disconnection_point_contacts_and_empty_material() {
        let a = polygon(&[(0, 0), (6, 0), (6, 6), (0, 6)]);
        for (b, op, code) in [
            (
                polygon(&[(1, 1), (2, 1), (2, 2), (1, 2)]),
                Operation::Difference,
                "unsupported_coaxial_result",
            ),
            (
                polygon(&[(8, 0), (9, 0), (9, 1), (8, 1)]),
                Operation::Union,
                "unsupported_coaxial_result",
            ),
            (
                polygon(&[(6, 6), (8, 6), (8, 8), (6, 8)]),
                Operation::Union,
                "invalid_polyhedron",
            ),
            (a.clone(), Operation::Difference, "empty_solid"),
            (
                polygon(&[(6, 0), (8, 0), (8, 6), (6, 6)]),
                Operation::Intersection,
                "empty_solid",
            ),
        ] {
            assert_eq!(combine("test", &a, &b, op).unwrap_err().code, code);
        }
    }
    #[test]
    fn rejects_oversized_computed_coordinates_before_subdivision() {
        let mut a = polygon(&[(0, 0), (4, 0), (4, 4), (0, 4)]);
        a[1][0] = Q::from_integer(num_bigint::BigInt::from(1) << 1024);
        let b = polygon(&[(0, 0), (2, 0), (2, 2), (0, 2)]);
        assert_eq!(
            combine("test", &a, &b, Operation::Union).unwrap_err().code,
            "polyhedral_limit"
        );
    }
    #[test]
    fn resolves_sub_float_gaps_and_partial_coincident_edges_exactly() {
        let a = polygon(&[(0, 0), (4, 0), (4, 4), (0, 4)]);
        let b = polygon(&[(4, 1), (6, 1), (6, 3), (4, 3)]);
        let joined = combine("test", &a, &b, Operation::Union).unwrap();
        assert_eq!(canonical(joined).len(), 8);
        let epsilon = Q::new(1.into(), num_bigint::BigInt::from(10).pow(40));
        let gap: Vec<Point> = b.iter().map(|p| [&p[0] + &epsilon, p[1].clone()]).collect();
        assert_eq!(
            combine("test", &a, &gap, Operation::Union)
                .unwrap_err()
                .code,
            "unsupported_coaxial_result"
        );
        let overlap: Vec<Point> = b.iter().map(|p| [&p[0] - &epsilon, p[1].clone()]).collect();
        let common = combine("test", &a, &overlap, Operation::Intersection).unwrap();
        let twice_area: Q = edges(&common)
            .map(|(u, v)| &u[0] * &v[1] - &v[0] * &u[1])
            .sum();
        assert_eq!(twice_area, epsilon * q(4));
    }
}
