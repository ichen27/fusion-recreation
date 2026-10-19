use super::*;
use crate::Feature;
use std::path::Path;
fn model(name: &str) -> Model {
    serde_json::from_slice(
        &std::fs::read(
            Path::new(env!("CARGO_MANIFEST_DIR"))
                .join("../../examples/ai-cad")
                .join(name),
        )
        .unwrap(),
    )
    .unwrap()
}
fn topology(m: &Model) -> Topology {
    inspect(Request {
        model: m.clone(),
        feature_id: m.features.last().unwrap().id().into(),
    })
    .unwrap_or_else(|e| panic!("{} {}", e.code, e.message))
}
#[test]
fn every_saved_model_has_valid_shared_surface_topology() {
    let root = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../examples/ai-cad");
    let mut count = 0;
    for dir in std::fs::read_dir(root).unwrap() {
        let dir = dir.unwrap().path();
        if !dir.is_dir() {
            continue;
        }
        for file in std::fs::read_dir(dir).unwrap() {
            let path = file.unwrap().path();
            if !path.to_string_lossy().ends_with(".model.json") {
                continue;
            }
            let model: Model = serde_json::from_slice(&std::fs::read(&path).unwrap()).unwrap();
            for body in crate::validate(&model).unwrap() {
                let result = inspect(Request {
                    model: model.clone(),
                    feature_id: body.feature_id,
                });
                if let Err(e) = result {
                    panic!("{}: {} {}", path.display(), e.code, e.message);
                }
                count += 1;
            }
        }
    }
    assert!(count >= 71);
}
#[test]
fn planar_shells_and_analytic_genus_are_reported() {
    let cavity = topology(&model("planar-booleans/cavity.model.json"));
    assert_eq!(cavity.shell_euler, vec![2, 2]);
    assert_eq!(cavity.components.len(), 1);
    let part = topology(&model("counterbores/plate.model.json"));
    assert_eq!(part.shell_euler, vec![-2]);
    assert_eq!(part.shells.len(), 1);
    assert_eq!(part.surfaces.len(), 12); // six outer planes + six hole surfaces.
    assert_eq!(part.faces.len(), 24); // four patches per cylinder.
    let blind = topology(&model("analytic-measurements/blind_plate.model.json"));
    assert_eq!(blind.shell_euler, vec![2]);
}
#[test]
fn damaged_edges_surfaces_and_ownership_are_rejected() {
    let good = topology(&model("counterbores/plate.model.json"));
    let mut broken = good.clone();
    broken.faces.pop();
    assert!(validate::check(&broken).is_err());
    let mut broken = good.clone();
    broken.faces[0].loops[0][0].forward ^= true;
    assert!(validate::check(&broken).is_err());
    let mut broken = good.clone();
    broken.vertices.push(["0".into(), "0".into(), "0".into()]);
    assert!(validate::check(&broken).is_err());
    let mut broken = good.clone();
    let arc = broken
        .edges
        .iter_mut()
        .find(|e| matches!(e.curve, Curve::QuarterCircle { .. }))
        .unwrap();
    if let Curve::QuarterCircle { radius, .. } = &mut arc.curve {
        *radius = "4".into();
    }
    assert!(validate::check(&broken).is_err());
    let mut broken = good.clone();
    let cylinder = broken
        .surfaces
        .values_mut()
        .find(|s| matches!(s.geometry, Surface::Cylinder { .. }))
        .unwrap();
    if let Surface::Cylinder { inward, .. } = &mut cylinder.geometry {
        *inward = !*inward;
    }
    assert!(validate::check(&broken).is_err());
    let mut broken = good.clone();
    let plane = broken
        .surfaces
        .values_mut()
        .find(|s| matches!(s.geometry, Surface::Plane { .. }))
        .unwrap();
    if let Surface::Plane { offset, .. } = &mut plane.geometry {
        *offset = "1/3".into();
    }
    assert!(validate::check(&broken).is_err());
    let mut broken = good.clone();
    broken.components = vec![vec![0], (1..good.faces.len()).collect()];
    assert!(validate::check(&broken).is_err());
    let mut broken = good.clone();
    broken.edges[0].vertices[0] = usize::MAX;
    assert!(validate::check(&broken).is_err());
    let mut broken = good.clone();
    for face in &mut broken.faces {
        for ring in &mut face.loops {
            *ring = reverse(ring);
        }
    }
    assert!(validate::check(&broken).is_err());
}
#[test]
fn authored_surface_names_survive_dimensions_winding_and_placement_but_not_hole_replacement() {
    let mut original = model("counterbores/plate.model.json");
    let initial = topology(&original);
    let names: Vec<_> = initial.surfaces.keys().cloned().collect();
    original
        .parameters
        .insert("recess_depth".into(), "3".into());
    original
        .parameters
        .insert("recess_radius".into(), "6".into());
    match &mut original.features[0] {
        Feature::PolygonProfile { vertices, .. } | Feature::PlanarProfile { vertices, .. } => {
            vertices.reverse()
        }
        _ => panic!(),
    };
    assert_eq!(
        names,
        topology(&original)
            .surfaces
            .keys()
            .cloned()
            .collect::<Vec<_>>()
    );
    let placed = topology(&model("counterbores/turned.model.json"));
    assert_eq!(names, placed.surfaces.keys().cloned().collect::<Vec<_>>());
    match original.features.last_mut().unwrap() {
        Feature::CounterboreHoles { holes, .. } => holes[0].id = "new_hole".into(),
        _ => panic!(),
    };
    let changed = topology(&original);
    assert!(!changed.surfaces.keys().any(|s| s.contains("/hole/left/")));
    assert!(changed
        .surfaces
        .keys()
        .any(|s| s.contains("/hole/new_hole/")));
}
#[test]
fn conical_support_rejects_damaged_radii_height_axis_and_generators() {
    let m: Model = serde_json::from_value(serde_json::json!({
        "parameters":{"x":"0","y":"0","r0":"10","r1":"5","h":"12"},
        "features":[{"kind":"conical_frustum","id":"taper","x":"x","y":"y","bottom_radius":"r0","top_radius":"r1","height":"h"}],
        "fixed":{}
    })).unwrap();
    let good = topology(&m);
    for damage in 0..5 {
        let mut broken = good.clone();
        let support = &mut broken
            .surfaces
            .get_mut("feature/taper/outer/frustum")
            .unwrap()
            .geometry;
        if let Surface::ConicalFrustum {
            bottom_radius,
            top_radius,
            height,
            axis,
            origin,
            ..
        } = support
        {
            match damage {
                0 => *bottom_radius = "9".into(),
                1 => *top_radius = "6".into(),
                2 => *height = "11".into(),
                3 => *axis = [0, 0, -1],
                _ => origin[0] = "1/3".into(),
            }
        } else {
            panic!();
        }
        assert!(validate::check(&broken).is_err());
    }
    let mut broken = good.clone();
    let generators: Vec<_> = broken
        .edges
        .iter()
        .enumerate()
        .filter(|(_, e)| matches!(e.curve, Curve::Line))
        .map(|(i, _)| i)
        .collect();
    assert_eq!(generators.len(), 4);
    let end = broken.edges[generators[1]].vertices[1];
    broken.edges[generators[0]].vertices[1] = end;
    assert!(validate::check(&broken).is_err());
}
#[test]
fn inward_conical_recess_orientation_is_checked() {
    let mut m = model("counterbores/plate.model.json");
    let hole = m.features.last_mut().unwrap();
    if let Feature::CounterboreHoles {
        id,
        input,
        depth,
        bore_radius,
        holes,
    } = hole.clone()
    {
        *hole = Feature::CountersinkHoles {
            id,
            input,
            depth,
            rim_radius: bore_radius,
            holes,
        };
    } else {
        panic!();
    }
    let mut broken = topology(&m);
    let surface = &mut broken
        .surfaces
        .get_mut("feature/part/hole/left/taper")
        .unwrap()
        .geometry;
    if let Surface::ConicalFrustum { inward, .. } = surface {
        assert!(*inward);
        *inward = false;
    } else {
        panic!();
    }
    assert!(validate::check(&broken).is_err());
}
