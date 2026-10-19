use super::{fail, Result};
use crate::Q;
use num_traits::{Signed, Zero};

pub(super) type Point = [Q; 3];
pub(super) type Polygon = Vec<Point>;
pub(super) fn q(n: i32) -> Q {
    Q::from_integer(n.into())
}
pub(super) fn add(a: &Point, b: &Point) -> Point {
    std::array::from_fn(|i| &a[i] + &b[i])
}
pub(super) fn sub(a: &Point, b: &Point) -> Point {
    std::array::from_fn(|i| &a[i] - &b[i])
}
pub(super) fn mul(a: &Point, t: &Q) -> Point {
    std::array::from_fn(|i| &a[i] * t)
}
pub(super) fn dot(a: &Point, b: &Point) -> Q {
    (0..3).map(|i| &a[i] * &b[i]).sum()
}
pub(super) fn cross(a: &Point, b: &Point) -> Point {
    [
        &a[1] * &b[2] - &a[2] * &b[1],
        &a[2] * &b[0] - &a[0] * &b[2],
        &a[0] * &b[1] - &a[1] * &b[0],
    ]
}
pub(super) fn nonzero(a: &Point) -> bool {
    a.iter().any(|v| !v.is_zero())
}
pub(super) fn value(s: &str) -> Result<Q> {
    let value: Q = s.parse().map_err(|_| fail("Invalid computed rational"))?;
    if value.numer().bits() > 1024 || value.denom().bits() > 1024 {
        return Err(fail("Computed rational exceeds 1024 bits"));
    }
    Ok(value)
}
pub(super) fn point(p: &[String; 3]) -> Result<Point> {
    Ok([value(&p[0])?, value(&p[1])?, value(&p[2])?])
}
pub(super) fn clean(poly: Polygon) -> Polygon {
    let mut out = Vec::new();
    for p in poly {
        if out.last() != Some(&p) {
            out.push(p);
        }
    }
    if out.len() > 1 && out.first() == out.last() {
        out.pop();
    }
    while out.len() >= 3 {
        let redundant = (0..out.len()).find(|&i| {
            !nonzero(&cross(
                &sub(&out[i], &out[(i + out.len() - 1) % out.len()]),
                &sub(&out[(i + 1) % out.len()], &out[i]),
            ))
        });
        if let Some(i) = redundant {
            out.remove(i);
        } else {
            break;
        }
    }
    if out.len() < 3 {
        vec![]
    } else {
        out
    }
}
pub(super) fn plane(poly: &Polygon) -> (Point, Q) {
    let n = cross(&sub(&poly[1], &poly[0]), &sub(&poly[2], &poly[0]));
    let d = dot(&n, &poly[0]);
    (n, d)
}
pub(super) fn loop_vector(poly: &Polygon) -> Point {
    let mut sum = [q(0), q(0), q(0)];
    for i in 0..poly.len() {
        sum = add(&sum, &cross(&poly[i], &poly[(i + 1) % poly.len()]));
    }
    sum
}
pub(super) fn clip(poly: &Polygon, n: &Point, d: &Q) -> Polygon {
    let mut out = Vec::new();
    for i in 0..poly.len() {
        let a = &poly[i];
        let b = &poly[(i + 1) % poly.len()];
        let da = dot(n, a) - d;
        let db = dot(n, b) - d;
        if da <= q(0) {
            out.push(a.clone());
        }
        if (da.is_negative() && db.is_positive()) || (db.is_negative() && da.is_positive()) {
            out.push(add(a, &mul(&sub(b, a), &(&da / (&da - &db)))));
        }
    }
    clean(out)
}
pub(super) fn subtract(subject: &Polygon, cutter: &Polygon) -> Vec<Polygon> {
    let (n, _) = plane(cutter);
    let mut rest = subject.clone();
    let mut pieces = Vec::new();
    for i in 0..cutter.len() {
        let a = &cutter[i];
        let b = &cutter[(i + 1) % cutter.len()];
        let edge = cross(&sub(b, a), &n);
        let d = dot(&edge, a);
        let outside = clip(&rest, &mul(&edge, &q(-1)), &(-&d));
        if !outside.is_empty() {
            pieces.push(outside);
        }
        rest = clip(&rest, &edge, &d);
        if rest.is_empty() {
            break;
        }
    }
    pieces
}
pub(super) fn overlap(a: &Polygon, b: &Polygon) -> bool {
    let (n, _) = plane(b);
    let mut rest = a.clone();
    for i in 0..b.len() {
        let edge = cross(&sub(&b[(i + 1) % b.len()], &b[i]), &n);
        rest = clip(&rest, &edge, &dot(&edge, &b[i]));
        if rest.is_empty() {
            return false;
        }
    }
    true
}
pub(super) fn inside(p: &Point, poly: &Polygon, n: &Point) -> Result<bool> {
    let drop = (0..3).max_by_key(|&i| n[i].abs()).unwrap();
    let axes: Vec<_> = (0..3).filter(|&i| i != drop).collect();
    let (x, y) = (axes[0], axes[1]);
    let mut result = false;
    for i in 0..poly.len() {
        let a = &poly[i];
        let b = &poly[(i + 1) % poly.len()];
        if !nonzero(&cross(&sub(b, a), &sub(p, a)))
            && (0..3).all(|k| {
                p[k] >= a[k].clone().min(b[k].clone()) && p[k] <= a[k].clone().max(b[k].clone())
            })
        {
            return Err(fail("Touching face loops are unsupported"));
        }
        if (a[y] > p[y]) != (b[y] > p[y]) {
            let crossing = &a[x] + (&p[y] - &a[y]) * (&b[x] - &a[x]) / (&b[y] - &a[y]);
            if p[x] < crossing {
                result = !result;
            }
        }
    }
    Ok(result)
}
