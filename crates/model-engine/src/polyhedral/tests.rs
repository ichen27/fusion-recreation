use super::math::*;
use super::*;

fn box_at(lo: Point, hi: Point) -> Solid {
    let mut boundary = crate::block(&(&hi[0] - &lo[0]), &(&hi[1] - &lo[1]), &(&hi[2] - &lo[2]));
    for p in &mut boundary.vertices {
        for i in 0..3 {
            p[i] = (value(&p[i]).unwrap() + &lo[i]).to_string();
        }
    }
    for f in &mut boundary.faces {
        let n = point(&f.normal).unwrap();
        f.offset = (value(&f.offset).unwrap() + dot(&n, &lo)).to_string();
    }
    Solid::from_convex(boundary).unwrap()
}
fn cube(lo: [i32; 3], hi: [i32; 3]) -> Solid {
    box_at(lo.map(q), hi.map(q))
}

#[test]
fn overlapping_union_and_full_face_contact_remove_internal_seams() {
    for start in [1, 2] {
        let result = cube([0, 0, 0], [2, 2, 2])
            .combine(&cube([start, 0, 0], [start + 2, 2, 2]), Operation::Union)
            .unwrap();
        assert_eq!(result.volume, q((start + 2) * 4));
        assert_eq!(result.boundary.faces.len(), 6);
        assert_eq!(result.boundary.vertices.len(), 8);
        assert_eq!(result.components.len(), 1);
    }
}
#[test]
fn l_shape_cavity_holes_and_separated_components() {
    let l = cube([0, 0, 0], [2, 1, 1])
        .combine(&cube([0, 1, 0], [1, 2, 1]), Operation::Union)
        .unwrap();
    assert_eq!(l.volume, q(3));
    assert_eq!(l.boundary.faces.len(), 8);
    let outer = cube([0, 0, 0], [10, 10, 10]);
    let cavity = outer
        .combine(&cube([2, 2, 2], [8, 8, 8]), Operation::Difference)
        .unwrap();
    assert_eq!(cavity.volume, q(784));
    assert_eq!(cavity.components.len(), 1);
    assert_eq!(cavity.boundary.faces.len(), 12);
    let hole = outer
        .combine(&cube([2, 2, -1], [8, 8, 11]), Operation::Difference)
        .unwrap();
    assert_eq!(hole.volume, q(640));
    assert_eq!(hole.boundary.faces.len(), 10);
    assert_eq!(
        hole.boundary
            .faces
            .iter()
            .filter(|f| f.loops.len() == 2)
            .count(),
        2
    );
    let split = outer
        .combine(&cube([4, -1, -1], [6, 11, 11]), Operation::Difference)
        .unwrap();
    assert_eq!(split.volume, q(800));
    assert_eq!(split.components.len(), 2);
    assert_eq!(split.boundary.faces.len(), 12);
    let disjoint = cube([0, 0, 0], [1, 1, 1])
        .combine(&cube([3, 0, 0], [4, 1, 1]), Operation::Union)
        .unwrap();
    assert_eq!(disjoint.volume, q(2));
    assert_eq!(disjoint.components.len(), 2);
}
#[test]
fn repeated_edits_and_filling_a_cavity_restore_outer_boundary() {
    let outer = cube([0, 0, 0], [10, 10, 10]);
    let inner = cube([2, 2, 2], [8, 8, 8]);
    let cavity = outer.combine(&inner, Operation::Difference).unwrap();
    let repeated = cavity.combine(&inner, Operation::Difference).unwrap();
    assert_eq!(repeated.volume, cavity.volume);
    let restored = repeated.combine(&inner, Operation::Union).unwrap();
    assert_eq!(restored.volume, q(1000));
    assert_eq!(restored.boundary.faces.len(), 6);
    assert_eq!(restored.boundary.vertices.len(), 8);
    let common = restored
        .combine(&cube([5, 5, 5], [15, 15, 15]), Operation::Intersection)
        .unwrap();
    assert_eq!(common.volume, q(125));
}
#[test]
fn touching_edges_points_and_empty_results_reject() {
    let a = cube([0, 0, 0], [1, 1, 1]);
    for b in [cube([1, 1, 0], [2, 2, 1]), cube([1, 1, 1], [2, 2, 2])] {
        assert_eq!(
            a.combine(&b, Operation::Union).unwrap_err().code,
            "invalid_polyhedron"
        );
    }
    assert_eq!(
        a.combine(&a, Operation::Difference).unwrap_err().code,
        "empty_solid"
    );
    assert_eq!(
        a.combine(&cube([1, 0, 0], [2, 1, 1]), Operation::Intersection)
            .unwrap_err()
            .code,
        "empty_solid"
    );
}
#[test]
fn exact_thin_wall_and_oblique_faces() {
    let epsilon: Q = "1/100000000000000000000".parse().unwrap();
    let outer = cube([0, 0, 0], [1, 1, 1]);
    let cutter = box_at([q(0), q(0), epsilon.clone()], [q(1), q(1), q(2)]);
    let wall = outer.combine(&cutter, Operation::Difference).unwrap();
    assert_eq!(wall.volume, epsilon);
    let reply = boundary_clip::clip(boundary_clip::Request {
        schema_version: 1,
        boundary: outer.boundary.clone(),
        plane: boundary_clip::Plane {
            normal: ["1".into(), "1".into(), "1".into()],
            offset: "1".into(),
        },
    })
    .unwrap();
    let tetra = Solid::from_convex(reply.boundary).unwrap();
    assert_eq!(tetra.volume, q(1) / q(6));
    let result = tetra
        .combine(&cube([2, 2, 2], [3, 3, 3]), Operation::Union)
        .unwrap();
    assert_eq!(result.volume, q(7) / q(6));
    assert_eq!(result.components.len(), 2);
}
#[test]
fn invalid_inputs_and_cell_budget_are_checked() {
    let cube = cube([0, 0, 0], [1, 1, 1]);
    let mut bad = cube.boundary.clone();
    bad.edges[0].vertices[0] = usize::MAX;
    assert!(Solid::from_convex(bad).is_err());
    assert_eq!(
        Solid::from_cells(vec![cube.boundary; 33]).unwrap_err().code,
        "polyhedral_limit"
    );
}
