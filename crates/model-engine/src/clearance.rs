//! Exact minimum separation of bounded planar solids, with rational witnesses.
use crate::topology::{dot, output, point, sub, Point};
use crate::{error, interference, Boundary, Result, Q};
use num_traits::{One, Signed, ToPrimitive, Zero};
use serde::Serialize;

pub use interference::Request;
const MAX_CANDIDATES: usize = 200_000;
#[derive(Serialize)]
pub struct Clearance {
    pub left: String,
    pub right: String,
    pub relation: &'static str,
    pub distance_squared_mm2: String,
    pub distance_mm: String,
    pub distance_approx_mm: f64,
    pub closest_points_mm: Option<[[String; 3]; 2]>,
}
struct Cell {
    points: Vec<Point>,
    planes: Vec<(Point, Q)>,
    edges: Vec<[usize; 2]>,
}
impl Cell {
    fn new(boundary: &Boundary) -> Result<Self> {
        Ok(Self {
            points: boundary.vertices.iter().map(point).collect::<Result<_>>()?,
            planes: boundary
                .faces
                .iter()
                .map(|f| Ok((point(&f.normal)?, crate::measure::value(&f.offset)?)))
                .collect::<Result<_>>()?,
            edges: boundary.edges.iter().map(|e| e.vertices).collect(),
        })
    }
    fn contains(&self, p: &Point) -> bool {
        self.planes.iter().all(|(n, d)| dot(n, p) <= *d)
    }
}
fn along(a: &Point, v: &Point, t: &Q) -> Point {
    std::array::from_fn(|i| &a[i] + &v[i] * t)
}
fn clamp(t: Q) -> Q {
    t.max(Q::zero()).min(Q::one())
}
fn projection(p: &Point, a: &Point, b: &Point) -> Point {
    let v = sub(b, a);
    along(a, &v, &clamp(dot(&sub(p, a), &v) / dot(&v, &v)))
}
struct Search {
    best: Option<(Q, Point, Point)>,
    candidates: usize,
}
impl Search {
    fn tick(&mut self) -> Result<()> {
        self.candidates += 1;
        if self.candidates > MAX_CANDIDATES {
            return Err(error(
                "clearance_limit",
                "clearance",
                "Maximum 200000 feature comparisons; split the query into simpler parts",
            ));
        }
        Ok(())
    }
    fn add(&mut self, a: Point, b: Point) -> Result<()> {
        let d = sub(&a, &b);
        let squared = dot(&d, &d);
        crate::measure::bounded(&squared)?;
        if self.best.as_ref().is_none_or(|best| squared < best.0) {
            self.best = Some((squared, a, b));
        }
        Ok(())
    }
    fn vertex_faces(&mut self, a: &Cell, b: &Cell, reverse: bool) -> Result<()> {
        for p in &a.points {
            for (normal, offset) in &b.planes {
                self.tick()?;
                let scale = (offset - dot(normal, p)) / dot(normal, normal);
                let q = along(p, normal, &scale);
                if b.contains(&q) {
                    if reverse {
                        self.add(q, p.clone())?;
                    } else {
                        self.add(p.clone(), q)?;
                    }
                }
            }
        }
        Ok(())
    }
    fn edge_pair(&mut self, a: [&Point; 2], b: [&Point; 2]) -> Result<()> {
        self.tick()?;
        // Boundary minima, including parallel and collinear segments.
        for p in a {
            self.add(p.clone(), projection(p, b[0], b[1]))?;
        }
        for p in b {
            self.add(projection(p, a[0], a[1]), p.clone())?;
        }
        let u = sub(a[1], a[0]);
        let v = sub(b[1], b[0]);
        let w = sub(a[0], b[0]);
        let aa = dot(&u, &u);
        let bb = dot(&u, &v);
        let cc = dot(&v, &v);
        let dd = dot(&u, &w);
        let ee = dot(&v, &w);
        let determinant = &aa * &cc - &bb * &bb;
        if determinant.is_positive() {
            let s = (&bb * &ee - &cc * &dd) / &determinant;
            let t = (&aa * &ee - &bb * &dd) / &determinant;
            if s >= Q::zero() && s <= Q::one() && t >= Q::zero() && t <= Q::one() {
                self.add(along(a[0], &u, &s), along(b[0], &v, &t))?;
            }
        }
        Ok(())
    }
    fn pair(&mut self, a: &Cell, b: &Cell) -> Result<()> {
        self.vertex_faces(a, b, false)?;
        self.vertex_faces(b, a, true)?;
        for edge_a in &a.edges {
            for edge_b in &b.edges {
                self.edge_pair(edge_a.map(|i| &a.points[i]), edge_b.map(|i| &b.points[i]))?;
            }
        }
        Ok(())
    }
}
fn squared_gap(a: &[[Q; 3]; 2], b: &[[Q; 3]; 2]) -> Q {
    (0..3)
        .map(|i| {
            let gap = (&a[0][i] - &b[1][i])
                .max(&b[0][i] - &a[1][i])
                .max(Q::zero());
            &gap * &gap
        })
        .sum()
}
pub fn inspect(request: Request) -> Result<Clearance> {
    let (left,right)=interference::prepare(&request).map_err(|e| {
        if e.code=="unsupported_interference" {
            error("unsupported_clearance",&e.entity,"Exact separation currently requires planar bodies; curved/perforated analytic stock is unsupported")
        } else {e}
    })?;
    let left_bounds = left
        .iter()
        .map(interference::bounds)
        .collect::<Result<Vec<_>>>()?;
    let right_bounds = right
        .iter()
        .map(interference::bounds)
        .collect::<Result<Vec<_>>>()?;
    let mut pairs = Vec::new();
    // Establish interior disjointness before minimizing boundary distance. For
    // overlapping solids, boundary-to-boundary distance is not material separation.
    for (i, a) in left.iter().enumerate() {
        for (j, b) in right.iter().enumerate() {
            let ab = &left_bounds[i];
            let bb = &right_bounds[j];
            if (0..3).all(|axis| ab[1][axis] > bb[0][axis] && bb[1][axis] > ab[0][axis]) {
                match crate::solid_ops::intersection("clearance", a.clone(), b) {
                    Ok(_) => {
                        return Ok(Clearance {
                            left: request.left,
                            right: request.right,
                            relation: "overlapping",
                            distance_squared_mm2: "0".into(),
                            distance_mm: "0".into(),
                            distance_approx_mm: 0.0,
                            closest_points_mm: None,
                        })
                    }
                    Err(e) if e.code == "empty_solid" => {}
                    Err(e) => return Err(e),
                }
            }
            pairs.push((squared_gap(ab, bb), i, j));
        }
    }
    pairs.sort();
    let left = left.iter().map(Cell::new).collect::<Result<Vec<_>>>()?;
    let right = right.iter().map(Cell::new).collect::<Result<Vec<_>>>()?;
    let mut search = Search {
        best: None,
        candidates: 0,
    };
    for (lower, i, j) in pairs {
        if search.best.as_ref().is_some_and(|best| lower >= best.0) {
            continue;
        }
        search.pair(&left[i], &right[j])?;
    }
    let (squared, a, b) = search.best.ok_or_else(|| {
        error(
            "invalid_geometry",
            "clearance",
            "No closest feature pair found",
        )
    })?;
    let approx = squared.to_f64().unwrap_or(f64::NAN).sqrt();
    if !approx.is_finite() {
        return Err(error(
            "clearance_limit",
            "clearance",
            "Distance exceeds floating display range",
        ));
    }
    Ok(Clearance {
        left: request.left,
        right: request.right,
        relation: if squared.is_zero() {
            "touching"
        } else {
            "separated"
        },
        distance_mm: crate::edge_measure::root(&squared),
        distance_squared_mm2: squared.to_string(),
        distance_approx_mm: approx,
        closest_points_mm: Some([output(&a), output(&b)]),
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    fn p(values: [&str; 3]) -> Point {
        values.map(|s| s.parse().unwrap())
    }
    #[test]
    fn skew_edges_choose_interior_closest_points() {
        let a = [p(["-1", "0", "0"]), p(["1", "0", "0"])];
        let b = [p(["0", "-1", "2"]), p(["0", "1", "2"])];
        let mut search = Search {
            best: None,
            candidates: 0,
        };
        search.edge_pair([&a[0], &a[1]], [&b[0], &b[1]]).unwrap();
        let (squared, x, y) = search.best.unwrap();
        assert_eq!(squared, "4".parse::<Q>().unwrap());
        assert_eq!(x, p(["0", "0", "0"]));
        assert_eq!(y, p(["0", "0", "2"]));
    }
    #[test]
    fn parallel_and_endpoint_minima_are_exact() {
        for (a, b, expected) in [
            (
                [p(["0", "0", "0"]), p(["1", "0", "0"])],
                [p(["2", "0", "0"]), p(["3", "0", "0"])],
                "1",
            ),
            (
                [p(["0", "0", "0"]), p(["1", "0", "0"])],
                [p(["1/2", "1/3", "0"]), p(["2", "1/3", "0"])],
                "1/9",
            ),
            (
                [p(["0", "0", "0"]), p(["1", "0", "0"])],
                [p(["2", "1", "0"]), p(["2", "2", "0"])],
                "2",
            ),
        ] {
            let mut search = Search {
                best: None,
                candidates: 0,
            };
            search.edge_pair([&a[0], &a[1]], [&b[0], &b[1]]).unwrap();
            assert_eq!(search.best.unwrap().0, expected.parse::<Q>().unwrap());
        }
    }
    #[test]
    fn exhausted_comparison_budget_rejects_instead_of_returning_partial_distance() {
        let mut search = Search {
            best: None,
            candidates: MAX_CANDIDATES,
        };
        assert_eq!(search.tick().unwrap_err().code, "clearance_limit");
    }
}
