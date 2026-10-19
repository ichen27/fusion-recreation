use super::math::*;
use super::{fail, limit, Result, MAX_EDGES, MAX_FACES, MAX_PATCHES, MAX_VERTICES};
use crate::Q;
use boundary_clip::{Boundary, Edge, Face, Use};
use num_traits::{Signed, Zero};
use std::collections::{BTreeMap, BTreeSet};

type PlaneKey = [Q; 4];
type EdgeOwners = BTreeMap<(Point, Point), Vec<(usize, Point, Point)>>;
type Groups = BTreeMap<PlaneKey, BTreeMap<i32, Vec<(usize, Polygon)>>>;
#[derive(Clone)]
struct PatchFace {
    normal: Point,
    offset: Q,
    loops: Vec<Polygon>,
    component: usize,
}
fn canonical(poly: &Polygon) -> (PlaneKey, i32) {
    let (normal, offset) = plane(poly);
    let pivot = normal.iter().find(|v| !v.is_zero()).unwrap();
    (
        [
            &normal[0] / pivot,
            &normal[1] / pivot,
            &normal[2] / pivot,
            offset / pivot,
        ],
        if pivot.is_positive() { 1 } else { -1 },
    )
}
fn root(parents: &[usize], mut i: usize) -> usize {
    while parents[i] != i {
        i = parents[i];
    }
    i
}
fn patch_budget(pieces: &[Polygon]) -> Result<()> {
    if pieces.len() > MAX_PATCHES || pieces.iter().map(Vec::len).sum::<usize>() > 8192 {
        return Err(limit("Planar patch subdivision budget exceeded"));
    }
    for p in pieces.iter().flatten() {
        for v in p {
            if v.numer().bits() > 1024 || v.denom().bits() > 1024 {
                return Err(limit("Computed planar coordinate exceeds 1024 bits"));
            }
        }
    }
    Ok(())
}
fn split_edge(a: &Point, b: &Point, vertices: &BTreeSet<Point>) -> Vec<Point> {
    let v = sub(b, a);
    let axis = (0..3).find(|&i| !v[i].is_zero()).unwrap();
    let mut points = BTreeMap::from([(q(0), a.clone()), (q(1), b.clone())]);
    for p in vertices {
        let u = sub(p, a);
        if nonzero(&cross(&u, &v)) {
            continue;
        }
        let t = &u[axis] / &v[axis];
        if t > q(0) && t < q(1) {
            points.insert(t, p.clone());
        }
    }
    points.into_values().collect()
}
fn loops(mut edges: BTreeSet<(Point, Point)>) -> Result<Vec<Polygon>> {
    let mut outgoing: BTreeMap<Point, Vec<Point>> = BTreeMap::new();
    let mut incoming: BTreeMap<Point, usize> = BTreeMap::new();
    for (a, b) in &edges {
        outgoing.entry(a.clone()).or_default().push(b.clone());
        *incoming.entry(b.clone()).or_default() += 1;
    }
    if outgoing
        .iter()
        .any(|(p, next)| next.len() != 1 || incoming.get(p) != Some(&1))
        || incoming.len() != outgoing.len()
    {
        return Err(fail("Nonmanifold or touching planar patch boundary"));
    }
    let mut result = vec![];
    while let Some((start, _)) = edges.first().cloned() {
        let mut poly = vec![];
        let mut p = start.clone();
        loop {
            poly.push(p.clone());
            let next = outgoing[&p][0].clone();
            if !edges.remove(&(p, next.clone())) {
                return Err(fail("Broken boundary loop"));
            }
            p = next;
            if p == start {
                break;
            }
        }
        if poly.len() < 3 {
            return Err(fail("Degenerate boundary loop"));
        }
        result.push(poly);
    }
    Ok(result)
}
fn volume(faces: &[PatchFace]) -> Q {
    faces
        .iter()
        .flat_map(|f| &f.loops)
        .flat_map(|l| (1..l.len() - 1).map(|i| dot(&l[0], &cross(&l[i], &l[i + 1])) / q(6)))
        .sum()
}
fn validate(faces: &[PatchFace]) -> Result<()> {
    let mut owners: EdgeOwners = BTreeMap::new();
    for (index, face) in faces.iter().enumerate() {
        if !nonzero(&face.normal) {
            return Err(fail("Zero face normal"));
        }
        for (j, l) in face.loops.iter().enumerate() {
            if l.len() < 3 || l.iter().collect::<BTreeSet<_>>().len() != l.len() {
                return Err(fail("Degenerate face loop"));
            }
            if l.iter().any(|p| dot(&face.normal, p) != face.offset) {
                return Err(fail("Nonplanar face loop"));
            }
            let orientation = dot(&loop_vector(l), &face.normal);
            if (j == 0 && !orientation.is_positive()) || (j > 0 && !orientation.is_negative()) {
                return Err(fail("Incorrect face-loop orientation"));
            }
            for i in 0..l.len() {
                let a = &l[i];
                let b = &l[(i + 1) % l.len()];
                let key = if a < b {
                    (a.clone(), b.clone())
                } else {
                    (b.clone(), a.clone())
                };
                owners
                    .entry(key)
                    .or_default()
                    .push((index, a.clone(), b.clone()));
            }
        }
    }
    if owners.len() > MAX_EDGES {
        return Err(limit("Maximum 1024 merged boundary edges"));
    }
    let mut links: BTreeMap<Point, BTreeMap<usize, Vec<usize>>> = BTreeMap::new();
    let mut neighbors: BTreeMap<usize, BTreeSet<usize>> = BTreeMap::new();
    for ((a, b), uses) in &owners {
        if uses.len() != 2
            || uses[0].0 == uses[1].0
            || uses[0].1 != uses[1].2
            || uses[0].2 != uses[1].1
        {
            return Err(fail("Open or nonmanifold boundary edge"));
        }
        let (i, j) = (uses[0].0, uses[1].0);
        for p in [a, b] {
            let graph = links.entry(p.clone()).or_default();
            graph.entry(i).or_default().push(j);
            graph.entry(j).or_default().push(i);
        }
        neighbors.entry(i).or_default().insert(j);
        neighbors.entry(j).or_default().insert(i);
    }
    for graph in links.values() {
        if graph.values().any(|v| v.len() != 2) {
            return Err(fail("Nonmanifold vertex"));
        }
        let mut seen = BTreeSet::new();
        let mut stack = vec![*graph.keys().next().unwrap()];
        while let Some(i) = stack.pop() {
            if seen.insert(i) {
                stack.extend(&graph[&i]);
            }
        }
        if seen.len() != graph.len() {
            return Err(fail("Disconnected vertex link"));
        }
    }
    let mut unseen: BTreeSet<_> = (0..faces.len()).collect();
    while let Some(&first) = unseen.first() {
        let mut shell = BTreeSet::new();
        let mut stack = vec![first];
        while let Some(i) = stack.pop() {
            if shell.insert(i) {
                stack.extend(&neighbors[&i]);
            }
        }
        let vertices: BTreeSet<_> = shell
            .iter()
            .flat_map(|&i| faces[i].loops.iter().flatten())
            .collect();
        let edges = owners
            .values()
            .filter(|uses| shell.contains(&uses[0].0))
            .count();
        let euler = vertices.len() as i64 - edges as i64
            + shell
                .iter()
                .map(|&i| 2 - faces[i].loops.len() as i64)
                .sum::<i64>();
        if euler > 2 || euler % 2 != 0 {
            return Err(fail("Invalid orientable shell topology"));
        }
        let component = faces[first].component;
        if shell.iter().any(|&i| faces[i].component != component) {
            return Err(fail("Inconsistent connected component"));
        }
        for i in shell {
            unseen.remove(&i);
        }
    }
    if !volume(faces).is_positive() {
        return Err(fail("Nonpositive boundary volume"));
    }
    Ok(())
}

pub(super) fn build(cells: &[Boundary]) -> Result<(Boundary, Vec<Vec<usize>>, Q)> {
    let mut groups: Groups = BTreeMap::new();
    let mut cell_faces = vec![];
    for (index, cell) in cells.iter().enumerate() {
        let points = cell
            .vertices
            .iter()
            .map(point)
            .collect::<Result<Vec<_>>>()?;
        for face in &cell.faces {
            if face.loops.len() != 1 {
                return Err(fail("Backing cells must be convex"));
            }
            let poly: Polygon = face.loops[0]
                .iter()
                .map(|u| points[cell.edges[u.edge].vertices[usize::from(!u.forward)]].clone())
                .collect();
            if poly.len() < 3 {
                return Err(fail("Degenerate backing face"));
            }
            let (key, sign) = canonical(&poly);
            if key
                .iter()
                .any(|v| v.numer().bits() > 1024 || v.denom().bits() > 1024)
            {
                return Err(limit("Computed plane exceeds 1024 bits"));
            }
            groups
                .entry(key)
                .or_default()
                .entry(sign)
                .or_default()
                .push((index, poly.clone()));
            let (normal, offset) = plane(&poly);
            cell_faces.push(PatchFace {
                normal,
                offset,
                loops: vec![poly],
                component: index,
            });
        }
    }
    let cell_volume = volume(&cell_faces);
    let mut parents: Vec<_> = (0..cells.len()).collect();
    for sides in groups.values() {
        if let (Some(positive), Some(negative)) = (sides.get(&1), sides.get(&-1)) {
            for (a, p) in positive {
                for (b, q) in negative {
                    if overlap(p, q) {
                        let (ra, rb) = (root(&parents, *a), root(&parents, *b));
                        parents[ra.max(rb)] = ra.min(rb);
                    }
                }
            }
        }
    }
    let mut patches: BTreeMap<(PlaneKey, i32, usize), Vec<Polygon>> = BTreeMap::new();
    let mut total_patches = 0;
    for (key, sides) in &groups {
        for sign in [1, -1] {
            if let Some(polys) = sides.get(&sign) {
                for (cell, poly) in polys {
                    let mut pieces = vec![poly.clone()];
                    if let Some(cutters) = sides.get(&-sign) {
                        for (_, cutter) in cutters {
                            let mut next = vec![];
                            for part in &pieces {
                                for fragment in subtract(part, cutter) {
                                    next.push(fragment);
                                    patch_budget(&next)?;
                                }
                            }
                            pieces = next;
                            patch_budget(&pieces)?;
                            if pieces.is_empty() {
                                break;
                            }
                        }
                    }
                    if !pieces.is_empty() {
                        total_patches += pieces.len();
                        if total_patches > MAX_PATCHES {
                            return Err(limit("Maximum 512 exposed planar patches"));
                        }
                        let exposed = patches
                            .entry((key.clone(), sign, root(&parents, *cell)))
                            .or_default();
                        exposed.extend(pieces);
                        patch_budget(exposed)?;
                    }
                }
            }
        }
    }
    if patches.values().map(Vec::len).sum::<usize>() > MAX_PATCHES {
        return Err(limit("Maximum 512 exposed planar patches"));
    }
    let mut vertices = BTreeSet::new();
    for point in patches.values().flatten().flatten() {
        vertices.insert(point.clone());
        if vertices.len() > MAX_VERTICES {
            return Err(limit("Maximum 512 merged boundary vertices"));
        }
    }
    let mut faces = vec![];
    for ((key, sign, component), polys) in patches {
        let mut directed: BTreeMap<(Point, Point), i32> = BTreeMap::new();
        for poly in polys {
            for i in 0..poly.len() {
                let points = split_edge(&poly[i], &poly[(i + 1) % poly.len()], &vertices);
                for pair in points.windows(2) {
                    *directed
                        .entry((pair[0].clone(), pair[1].clone()))
                        .or_default() += 1;
                    if directed.len() > 8192 {
                        return Err(limit("Planar edge subdivision budget exceeded"));
                    }
                }
            }
        }
        let mut edges = BTreeSet::new();
        for ((a, b), count) in &directed {
            let net = count - directed.get(&(b.clone(), a.clone())).unwrap_or(&0);
            if net > 1 {
                return Err(fail("Overlapping planar patches"));
            }
            if net == 1 {
                edges.insert((a.clone(), b.clone()));
            }
        }
        if edges.is_empty() {
            continue;
        }
        let normal = mul(&[key[0].clone(), key[1].clone(), key[2].clone()], &q(sign));
        let offset = &key[3] * q(sign);
        let loops = loops(edges)?;
        let mut outers = vec![];
        let mut holes = vec![];
        for poly in loops {
            let orientation = dot(&loop_vector(&poly), &normal);
            if orientation.is_positive() {
                outers.push(poly);
            } else if orientation.is_negative() {
                holes.push(poly);
            } else {
                return Err(fail("Zero-area face loop"));
            }
        }
        let mut assigned = vec![vec![]; outers.len()];
        for hole in holes {
            let mut containers = vec![];
            for (i, outer) in outers.iter().enumerate() {
                if inside(&hole[0], outer, &normal)? {
                    containers.push(i);
                }
            }
            let selected = containers
                .into_iter()
                .min_by_key(|&i| dot(&loop_vector(&outers[i]), &normal))
                .ok_or_else(|| fail("Hole without enclosing outer face"))?;
            assigned[selected].push(hole);
        }
        for (outer, holes) in outers.into_iter().zip(assigned) {
            let mut loops = vec![outer];
            loops.extend(holes);
            faces.push(PatchFace {
                normal: normal.clone(),
                offset: offset.clone(),
                loops,
                component,
            });
        }
        if faces.len() > MAX_FACES {
            return Err(limit("Maximum 256 merged boundary faces"));
        }
    }
    // Remove a straight-edge point only when every incident loop agrees.
    let mut straight: BTreeMap<Point, bool> = BTreeMap::new();
    for l in faces.iter().flat_map(|f| &f.loops) {
        for i in 0..l.len() {
            let p = &l[i];
            let yes = !nonzero(&cross(
                &sub(p, &l[(i + l.len() - 1) % l.len()]),
                &sub(&l[(i + 1) % l.len()], p),
            ));
            *straight.entry(p.clone()).or_insert(true) &= yes;
        }
    }
    for l in faces.iter_mut().flat_map(|f| &mut f.loops) {
        l.retain(|p| !straight[p]);
    }
    validate(&faces)?;
    let boundary_volume = volume(&faces);
    if boundary_volume != cell_volume {
        return Err(fail("Merged boundary/cell volume mismatch"));
    }
    let vertices: Vec<Point> = faces
        .iter()
        .flat_map(|f| f.loops.iter().flatten())
        .cloned()
        .collect::<BTreeSet<_>>()
        .into_iter()
        .collect();
    let lookup: BTreeMap<_, _> = vertices
        .iter()
        .cloned()
        .enumerate()
        .map(|(i, p)| (p, i))
        .collect();
    let mut result = Boundary {
        vertices: vertices
            .iter()
            .map(|p| p.clone().map(|q| q.to_string()))
            .collect(),
        edges: vec![],
        faces: vec![],
    };
    let mut edge_map = BTreeMap::new();
    let mut components: BTreeMap<usize, Vec<usize>> = BTreeMap::new();
    for face in faces {
        let loops = face
            .loops
            .into_iter()
            .map(|l| {
                (0..l.len())
                    .map(|i| {
                        let (a, b) = (lookup[&l[i]], lookup[&l[(i + 1) % l.len()]]);
                        let key = [a.min(b), a.max(b)];
                        let edge = *edge_map.entry(key).or_insert_with(|| {
                            let index = result.edges.len();
                            result.edges.push(Edge {
                                kind: "line".into(),
                                vertices: key,
                            });
                            index
                        });
                        Use {
                            edge,
                            forward: a < b,
                        }
                    })
                    .collect()
            })
            .collect();
        components
            .entry(face.component)
            .or_default()
            .push(result.faces.len());
        result.faces.push(Face {
            kind: "plane".into(),
            normal: face.normal.map(|v| v.to_string()),
            offset: face.offset.to_string(),
            loops,
        });
    }
    Ok((result, components.into_values().collect(), boundary_volume))
}
