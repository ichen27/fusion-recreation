//! Exact, bounded convex clipping directly on an oriented planar boundary.
//! No geometry library, cell decomposition, triangulation or floating point.
#![forbid(unsafe_code)]

use num_bigint::BigInt;
use num_rational::BigRational as Q;
use num_traits::{Signed, Zero};
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet};

type Point = [Q; 3];
type Result<T> = std::result::Result<T, String>;
const MAX_VERTICES: usize = 128;
const MAX_FACES: usize = 128;
const MAX_EDGES: usize = 384;
const MAX_USES: usize = 768;
const MAX_BITS: u64 = 1024;
pub const MAX_REQUEST_BYTES: u64 = 1_048_576;

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Edge {
    pub kind: String,
    pub vertices: [usize; 2],
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Use {
    pub edge: usize,
    pub forward: bool,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Face {
    pub kind: String,
    pub normal: [String; 3],
    pub offset: String,
    pub loops: Vec<Vec<Use>>,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Boundary {
    pub vertices: Vec<[String; 3]>,
    pub edges: Vec<Edge>,
    pub faces: Vec<Face>,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Plane {
    pub normal: [String; 3],
    pub offset: String,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Request {
    pub schema_version: u32,
    pub boundary: Boundary,
    pub plane: Plane,
}

#[derive(Debug, Deserialize, Serialize)]
pub struct Reply {
    pub schema_version: u32,
    pub classification: String,
    pub boundary: Boundary,
    pub volume: String,
}

#[derive(Clone)]
struct Polygon {
    normal: Point,
    offset: Q,
    points: Vec<Point>,
}

fn rational(s: &str) -> Result<Q> {
    // Only integer or integer/integer strings. No implicit floating point.
    if s.len() > 620 {
        return Err("rational exceeds input size limit".into());
    }
    fn integer(s: &str) -> Result<BigInt> {
        let digits = s.strip_prefix('-').unwrap_or(s);
        if digits.is_empty() || !digits.bytes().all(|b| b.is_ascii_digit()) {
            return Err("expected an integer or rational string".into());
        }
        s.parse().map_err(|_| "invalid integer".into())
    }
    let (numerator, denominator) = s.split_once('/').unwrap_or((s, "1"));
    let n = integer(numerator)?;
    let d = integer(denominator)?;
    if d.is_zero() || n.bits() > MAX_BITS || d.bits() > MAX_BITS {
        return Err("zero denominator or rational bit limit exceeded".into());
    }
    Ok(Q::new(n, d))
}

fn point(p: &[String; 3]) -> Result<Point> {
    Ok([rational(&p[0])?, rational(&p[1])?, rational(&p[2])?])
}

fn sub(a: &Point, b: &Point) -> Point {
    std::array::from_fn(|i| &a[i] - &b[i])
}

fn dot(a: &Point, b: &Point) -> Q {
    (0..3).map(|i| &a[i] * &b[i]).sum()
}

fn cross(a: &Point, b: &Point) -> Point {
    [
        &a[1] * &b[2] - &a[2] * &b[1],
        &a[2] * &b[0] - &a[0] * &b[2],
        &a[0] * &b[1] - &a[1] * &b[0],
    ]
}

fn zero(p: &Point) -> bool {
    p.iter().all(Zero::is_zero)
}

fn area(points: &[Point]) -> Point {
    let mut sum = std::array::from_fn(|_| Q::zero());
    for i in 0..points.len() {
        let c = cross(&points[i], &points[(i + 1) % points.len()]);
        for j in 0..3 {
            sum[j] += &c[j];
        }
    }
    sum
}

fn volume(polygons: &[Polygon]) -> Q {
    let six = Q::from_integer(6.into());
    polygons
        .iter()
        .map(|p| {
            (1..p.points.len() - 1)
                .map(|i| dot(&p.points[0], &cross(&p.points[i], &p.points[i + 1])) / &six)
                .sum::<Q>()
        })
        .sum()
}

fn directed(boundary: &Boundary, u: &Use) -> Result<[usize; 2]> {
    let edge = boundary.edges.get(u.edge).ok_or("invalid edge reference")?;
    let [a, b] = edge.vertices;
    Ok(if u.forward { [a, b] } else { [b, a] })
}

fn decode(boundary: &Boundary) -> Result<Vec<Polygon>> {
    if boundary.vertices.len() > MAX_VERTICES
        || boundary.faces.len() > MAX_FACES
        || boundary.edges.len() > MAX_EDGES
    {
        return Err("boundary size limit exceeded".into());
    }
    if boundary.vertices.is_empty() && boundary.edges.is_empty() && boundary.faces.is_empty() {
        return Ok(vec![]);
    }
    let vertices = boundary
        .vertices
        .iter()
        .map(point)
        .collect::<Result<Vec<_>>>()?;
    if vertices.iter().collect::<BTreeSet<_>>().len() != vertices.len() {
        return Err("duplicate vertex coordinates".into());
    }
    let mut edge_keys = BTreeSet::new();
    for edge in &boundary.edges {
        let [a, b] = edge.vertices;
        if edge.kind != "line" {
            return Err("unsupported curve: only exact lines are accepted".into());
        }
        if a >= vertices.len() || b >= vertices.len() || a == b {
            return Err("invalid or degenerate edge".into());
        }
        if !edge_keys.insert((a.min(b), a.max(b))) {
            return Err("duplicate edge".into());
        }
    }
    let mut owners = vec![vec![]; boundary.edges.len()];
    let mut used_vertices = BTreeSet::new();
    let mut polygons = vec![];
    let mut uses = 0;
    for (face_id, face) in boundary.faces.iter().enumerate() {
        if face.kind != "plane" || face.loops.len() != 1 {
            return Err("unsupported face: requires one planar loop without holes".into());
        }
        let normal = point(&face.normal)?;
        let offset = rational(&face.offset)?;
        let loop_ = &face.loops[0];
        uses += loop_.len();
        if loop_.len() < 3 || uses > MAX_USES || zero(&normal) {
            return Err("invalid face or boundary use limit exceeded".into());
        }
        let mut points = vec![];
        let mut seen = BTreeSet::new();
        for (i, u) in loop_.iter().enumerate() {
            let [a, b] = directed(boundary, u)?;
            if b != directed(boundary, &loop_[(i + 1) % loop_.len()])?[0] || !seen.insert(a) {
                return Err("open loop or repeated face vertex".into());
            }
            owners[u.edge].push((face_id, u.forward));
            used_vertices.insert(a);
            points.push(vertices[a].clone());
        }
        if points.iter().any(|p| dot(&normal, p) != offset) {
            return Err("face vertex off supporting plane".into());
        }
        if dot(&area(&points), &normal) <= Q::zero() {
            return Err("degenerate or reversed face".into());
        }
        // Each oriented edge must support this convex face, including collinear subdivisions.
        for i in 0..points.len() {
            let edge = sub(&points[(i + 1) % points.len()], &points[i]);
            if points
                .iter()
                .any(|p| dot(&cross(&edge, &sub(p, &points[i])), &normal) < Q::zero())
            {
                return Err("nonconvex or self-intersecting face".into());
            }
        }
        // The whole body must lie on the interior side of every outward face.
        if vertices.iter().any(|p| dot(&normal, p) > offset) {
            return Err("unsupported nonconvex body or inward face".into());
        }
        polygons.push(Polygon {
            normal,
            offset,
            points,
        });
    }
    if used_vertices.len() != vertices.len() || polygons.len() < 4 {
        return Err("unused vertices or insufficient faces for a solid".into());
    }
    let mut graph = vec![BTreeSet::new(); polygons.len()];
    for entries in &owners {
        if entries.len() != 2 || entries[0].0 == entries[1].0 || entries[0].1 == entries[1].1 {
            return Err("open, nonmanifold or inconsistently oriented edge".into());
        }
        graph[entries[0].0].insert(entries[1].0);
        graph[entries[1].0].insert(entries[0].0);
    }
    let mut reached = BTreeSet::new();
    let mut pending = vec![0];
    while let Some(i) = pending.pop() {
        if reached.insert(i) {
            pending.extend(&graph[i]);
        }
    }
    if reached.len() != polygons.len()
        || vertices.len() as isize - boundary.edges.len() as isize + polygons.len() as isize != 2
    {
        return Err("requires one closed genus-zero shell".into());
    }
    // At each vertex the incident face links must form one cycle, not pinched shells.
    for vertex in 0..vertices.len() {
        let mut links: BTreeMap<usize, Vec<usize>> = BTreeMap::new();
        for (i, edge) in boundary.edges.iter().enumerate() {
            if edge.vertices.contains(&vertex) {
                let (a, b) = (owners[i][0].0, owners[i][1].0);
                links.entry(a).or_default().push(b);
                links.entry(b).or_default().push(a);
            }
        }
        if links.values().any(|adj| adj.len() != 2) {
            return Err("nonmanifold vertex".into());
        }
        let mut visited = BTreeSet::new();
        let mut stack = vec![*links.keys().next().ok_or("unused vertex")?];
        while let Some(i) = stack.pop() {
            if visited.insert(i) {
                stack.extend(&links[&i]);
            }
        }
        if visited.len() != links.len() {
            return Err("disconnected vertex link".into());
        }
    }
    if volume(&polygons) <= Q::zero() {
        return Err("solid must have positive volume".into());
    }
    Ok(polygons)
}

fn encode(polygons: &[Polygon]) -> Result<Boundary> {
    let mut vertices: Vec<Point> = vec![];
    let mut vertex_ids = BTreeMap::new();
    let mut edges = vec![];
    let mut edge_ids = BTreeMap::new();
    let mut faces = vec![];
    for polygon in polygons {
        let mut ids = vec![];
        for p in &polygon.points {
            let id = *vertex_ids.entry(p.clone()).or_insert_with(|| {
                vertices.push(p.clone());
                vertices.len() - 1
            });
            ids.push(id);
        }
        let mut loop_ = vec![];
        for i in 0..ids.len() {
            let (a, b) = (ids[i], ids[(i + 1) % ids.len()]);
            let key = (a.min(b), a.max(b));
            let edge = *edge_ids.entry(key).or_insert_with(|| {
                edges.push(Edge {
                    kind: "line".into(),
                    vertices: [key.0, key.1],
                });
                edges.len() - 1
            });
            loop_.push(Use {
                edge,
                forward: a < b,
            });
        }
        faces.push(Face {
            kind: "plane".into(),
            normal: polygon.normal.each_ref().map(ToString::to_string),
            offset: polygon.offset.to_string(),
            loops: vec![loop_],
        });
    }
    let boundary = Boundary {
        vertices: vertices
            .iter()
            .map(|p| p.each_ref().map(ToString::to_string))
            .collect(),
        edges,
        faces,
    };
    // Results obey the same limits and topology contract as subsequent inputs.
    decode(&boundary)?;
    Ok(boundary)
}

fn trim(polygon: &Polygon, normal: &Point, offset: &Q) -> Option<Polygon> {
    let mut points = vec![];
    for i in 0..polygon.points.len() {
        let a = &polygon.points[i];
        let b = &polygon.points[(i + 1) % polygon.points.len()];
        let da = dot(normal, a) - offset;
        let db = dot(normal, b) - offset;
        if da <= Q::zero() {
            points.push(a.clone());
        }
        if (da < Q::zero() && db > Q::zero()) || (da > Q::zero() && db < Q::zero()) {
            let t = &da / (&da - &db);
            points.push(std::array::from_fn(|j| &a[j] + &t * (&b[j] - &a[j])));
        }
    }
    if points.len() < 3 || zero(&area(&points)) {
        return None;
    }
    Some(Polygon {
        normal: polygon.normal.clone(),
        offset: polygon.offset.clone(),
        points,
    })
}

fn cap(polygons: &[Polygon], normal: &Point, offset: &Q) -> Result<Polygon> {
    // Open edges are the cut rim. Reverse their existing orientation to close the shell.
    type Segment = (Point, Point);
    let mut edges: BTreeMap<Segment, Vec<Segment>> = BTreeMap::new();
    for polygon in polygons {
        for i in 0..polygon.points.len() {
            let a = polygon.points[i].clone();
            let b = polygon.points[(i + 1) % polygon.points.len()].clone();
            let key = if a < b {
                (a.clone(), b.clone())
            } else {
                (b.clone(), a.clone())
            };
            edges.entry(key).or_default().push((a, b));
        }
    }
    let mut next = BTreeMap::new();
    for entries in edges.values() {
        match entries.as_slice() {
            [(a, b)] => {
                if dot(normal, a) != *offset
                    || dot(normal, b) != *offset
                    || next.insert(b.clone(), a.clone()).is_some()
                {
                    return Err("invalid cut rim".into());
                }
            }
            [(a, b), (c, d)] if a == d && b == c => {}
            _ => return Err("nonmanifold trimmed boundary".into()),
        }
    }
    let start = next.keys().next().ok_or("missing cut rim")?.clone();
    let mut current = start.clone();
    let mut points = vec![];
    while let Some(end) = next.remove(&current) {
        points.push(current);
        current = end;
    }
    if current != start || !next.is_empty() || points.len() < 3 {
        return Err("cut rim is not one closed loop".into());
    }
    Ok(Polygon {
        normal: normal.clone(),
        offset: offset.clone(),
        points,
    })
}

/// Keep n·p <= offset. Face/edge/point-only contact is the empty solid.
pub fn clip(request: Request) -> Result<Reply> {
    if request.schema_version != 1 {
        return Err("unsupported schema version".into());
    }
    let normal = point(&request.plane.normal)?;
    let offset = rational(&request.plane.offset)?;
    if zero(&normal) {
        return Err("zero clipping normal".into());
    }
    let polygons = decode(&request.boundary)?;
    let distances: Vec<Q> = polygons
        .iter()
        .flat_map(|p| &p.points)
        .map(|p| dot(&normal, p) - &offset)
        .collect();
    let inside = distances.iter().any(Signed::is_negative);
    let outside = distances.iter().any(Signed::is_positive);
    let (classification, result) = if !inside {
        ("empty", vec![])
    } else if !outside {
        ("unchanged", polygons)
    } else {
        let mut result: Vec<_> = polygons
            .iter()
            .filter_map(|p| trim(p, &normal, &offset))
            .collect();
        result.push(cap(&result, &normal, &offset)?);
        ("clipped", result)
    };
    Ok(Reply {
        schema_version: 1,
        classification: classification.into(),
        boundary: encode(&result)?,
        volume: volume(&result).to_string(),
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn exact_rational_parser() {
        assert_eq!(rational("-2/-4").unwrap(), rational("1/2").unwrap());
        assert!(rational("1/1000000000000000000000000000000").is_ok());
        for s in ["NaN", "1.5", "1e-30", "1/0", "", "+1", "1/2/3", " 1"] {
            assert!(rational(s).is_err(), "{s}");
        }
        assert!(rational(&"9".repeat(400)).is_err());
    }
    #[test]
    fn empty_and_invalid_plane() {
        let mut r = Request {
            schema_version: 1,
            boundary: Boundary {
                vertices: vec![],
                edges: vec![],
                faces: vec![],
            },
            plane: Plane {
                normal: ["1".into(), "0".into(), "0".into()],
                offset: "0".into(),
            },
        };
        assert_eq!(clip(r.clone()).unwrap().volume, "0");
        r.plane.normal[0] = "0".into();
        assert!(clip(r).is_err());
    }
}
