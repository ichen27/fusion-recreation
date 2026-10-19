use super::*;
use crate::{AnalyticPrism, Body, Feature};
use std::collections::BTreeMap;
struct Ring {
    vertices: Vec<usize>,
    edges: Vec<Use>,
}
struct Builder {
    topology: Topology,
    vertices: BTreeMap<Point, usize>,
    edges: BTreeMap<(usize, usize), Vec<usize>>,
}
impl Builder {
    fn new(id: &str, naming: &'static str) -> Self {
        Self {
            topology: Topology {
                feature_id: id.into(),
                naming,
                vertices: vec![],
                edges: vec![],
                surfaces: BTreeMap::new(),
                faces: vec![],
                components: vec![],
                shells: vec![],
                shell_euler: vec![],
            },
            vertices: BTreeMap::new(),
            edges: BTreeMap::new(),
        }
    }
    fn vertex(&mut self, p: Point) -> usize {
        if let Some(&id) = self.vertices.get(&p) {
            return id;
        }
        let id = self.topology.vertices.len();
        self.topology.vertices.push(output(&p));
        self.vertices.insert(p, id);
        id
    }
    fn edge(&mut self, a: usize, b: usize, curve: Curve) -> Use {
        let key = (a.min(b), a.max(b));
        for &id in self.edges.get(&key).into_iter().flatten() {
            let edge = &self.topology.edges[id];
            if edge.curve == curve {
                return Use {
                    edge: id,
                    forward: edge.vertices == [a, b],
                };
            }
        }
        let id = self.topology.edges.len();
        self.topology.edges.push(Edge {
            vertices: [a, b],
            curve,
        });
        self.edges.entry(key).or_default().push(id);
        Use {
            edge: id,
            forward: true,
        }
    }
    fn polygon(&mut self, points: &[[Q; 2]], z: &Q) -> Ring {
        let vertices: Vec<_> = points
            .iter()
            .map(|p| self.vertex([p[0].clone(), p[1].clone(), z.clone()]))
            .collect();
        let edges = (0..vertices.len())
            .map(|i| self.edge(vertices[i], vertices[(i + 1) % vertices.len()], Curve::Line))
            .collect();
        Ring { vertices, edges }
    }
    fn circle(&mut self, center: &[Q; 2], radius: &Q, z: &Q) -> Ring {
        let points: Vec<_> = [[1, 0], [0, 1], [-1, 0], [0, -1]]
            .map(|v| [&center[0] + q(v[0]) * radius, &center[1] + q(v[1]) * radius])
            .into();
        let vertices: Vec<_> = points
            .iter()
            .map(|p| self.vertex([p[0].clone(), p[1].clone(), z.clone()]))
            .collect();
        let curve = Curve::QuarterCircle {
            center: output(&[center[0].clone(), center[1].clone(), z.clone()]),
            axis: [0, 0, 1],
            radius: radius.to_string(),
        };
        let edges = (0..4)
            .map(|i| self.edge(vertices[i], vertices[(i + 1) % 4], curve.clone()))
            .collect();
        Ring { vertices, edges }
    }
    fn surface(&mut self, owner: &str, role: &str, geometry: Surface) -> String {
        let id = format!("feature/{owner}/{role}");
        self.topology.surfaces.insert(
            id.clone(),
            SurfaceRecord {
                owner_feature: owner.into(),
                geometry,
            },
        );
        id
    }
    fn face(&mut self, surface: &str, suffix: &str, loops: Vec<Vec<Use>>) {
        self.topology.faces.push(Face {
            id: format!("{surface}{suffix}"),
            surface: surface.into(),
            loops,
        });
    }
    fn cap(&mut self, owner: &str, role: &str, z: &Q, up: bool, loops: Vec<Vec<Use>>) {
        let sign = if up { 1 } else { -1 };
        let surface = self.surface(
            owner,
            role,
            Surface::Plane {
                normal: ["0".into(), "0".into(), sign.to_string()],
                offset: (q(sign) * z).to_string(),
            },
        );
        self.face(&surface, "", loops);
    }
    fn wall(&mut self, surfaces: &[String], bottom: &Ring, top: &Ring, inward: bool) {
        let n = bottom.vertices.len();
        let vertical: Vec<_> = (0..n)
            .map(|i| self.edge(bottom.vertices[i], top.vertices[i], Curve::Line))
            .collect();
        for i in 0..n {
            let j = (i + 1) % n;
            let uses = vec![
                bottom.edges[i],
                vertical[j],
                Use {
                    edge: top.edges[i].edge,
                    forward: !top.edges[i].forward,
                },
                Use {
                    edge: vertical[i].edge,
                    forward: !vertical[i].forward,
                },
            ];
            let surface = &surfaces[if surfaces.len() == 1 { 0 } else { i }];
            let suffix = if surfaces.len() == 1 {
                format!("/patch/{i}")
            } else {
                String::new()
            };
            self.face(
                surface,
                &suffix,
                vec![if inward { reverse(&uses) } else { uses }],
            );
        }
    }
    fn cylinder(
        &mut self,
        owner: &str,
        role: &str,
        center: &[Q; 2],
        radius: &Q,
        rings: (&Ring, &Ring),
        inward: bool,
    ) {
        let (bottom, top) = rings;
        let surface = self.surface(
            owner,
            role,
            Surface::Cylinder {
                origin: output(&[center[0].clone(), center[1].clone(), q(0)]),
                axis: [0, 0, 1],
                radius: radius.to_string(),
                inward,
            },
        );
        self.wall(&[surface], bottom, top, inward);
    }
}
fn owners<'a>(model: &'a Model, id: &str) -> Result<(&'a Feature, Option<&'a str>)> {
    let mut current = id;
    let mut holes = None;
    for _ in 0..32 {
        let f = model
            .features
            .iter()
            .find(|f| f.id() == current)
            .ok_or_else(|| fail("Missing analytic source"))?;
        match f {
            Feature::Translate { input, .. } | Feature::RotateQuarter { input, .. } => {
                current = input
            }
            Feature::Instance { source, .. } => current = source,
            Feature::ThroughHoles { input, id, .. }
            | Feature::BlindHoles { input, id, .. }
            | Feature::CounterboreHoles { input, id, .. }
            | Feature::CountersinkHoles { input, id, .. } => {
                holes = Some(id.as_str());
                current = input;
            }
            Feature::Extrude { .. } | Feature::Cylinder { .. } | Feature::ConicalFrustum { .. } => {
                return Ok((f, holes))
            }
            _ => return Err(fail("Unsupported analytic source")),
        }
    }
    Err(fail("Analytic source chain exceeds model budget"))
}
fn analytic(model: &Model, body: &Body, shape: &AnalyticPrism) -> Result<Topology> {
    let (source, hole_owner) = owners(model, &body.feature_id)?;
    let owner = source.id();
    let h = value(&shape.height)?;
    let mut b = Builder::new(&body.feature_id, "authored_surfaces");
    let (bottom, top) = if let Some(circle) = &shape.outer_circle {
        let center = [value(&circle.center[0])?, value(&circle.center[1])?];
        let r = value(&circle.radius)?;
        let bottom = b.circle(&center, &r, &q(0));
        let top_radius = shape
            .top_radius
            .as_ref()
            .map(|s| value(s))
            .transpose()?
            .unwrap_or(r.clone());
        let top = b.circle(&center, &top_radius, &h);
        if shape.top_radius.is_some() {
            let surface = b.surface(
                owner,
                "outer/frustum",
                Surface::ConicalFrustum {
                    origin: output(&[center[0].clone(), center[1].clone(), q(0)]),
                    axis: [0, 0, 1],
                    bottom_radius: r.to_string(),
                    top_radius: top_radius.to_string(),
                    height: h.to_string(),
                    inward: false,
                },
            );
            b.wall(&[surface], &bottom, &top, false);
        } else {
            b.cylinder(owner, "outer/cylinder", &center, &r, (&bottom, &top), false);
        }
        (bottom, top)
    } else {
        let points = shape
            .outer
            .iter()
            .map(|p| Ok([value(&p[0])?, value(&p[1])?]))
            .collect::<Result<Vec<_>>>()?;
        let Feature::Extrude { profile, .. } = source else {
            return Err(fail("Expected extrusion provenance"));
        };
        let vertices = match model.features.iter().find(|f| f.id() == profile) {
            Some(Feature::PlanarProfile { vertices, .. })
            | Some(Feature::PolygonProfile { vertices, .. }) => vertices,
            _ => return Err(fail("Expected profile provenance")),
        };
        let mut names = BTreeMap::new();
        for v in vertices {
            names.insert(
                [
                    crate::parameter(model, &v.x)?,
                    crate::parameter(model, &v.y)?,
                ],
                v.id.clone(),
            );
        }
        let bottom = b.polygon(&points, &q(0));
        let top = b.polygon(&points, &h);
        let mut surfaces = vec![];
        for i in 0..points.len() {
            let (a, c) = (&points[i], &points[(i + 1) % points.len()]);
            let dx = &c[0] - &a[0];
            let dy = &c[1] - &a[1];
            let normal = [dy, -dx, q(0)];
            let mut pair = [names[a].clone(), names[c].clone()];
            pair.sort();
            surfaces.push(b.surface(
                owner,
                &format!("outer/side/{}/{}", pair[0], pair[1]),
                Surface::Plane {
                    normal: output(&normal),
                    offset: (&normal[0] * &a[0] + &normal[1] * &a[1]).to_string(),
                },
            ));
        }
        b.wall(&surfaces, &bottom, &top, false);
        (bottom, top)
    };
    let mut bottom_loops = vec![reverse(&bottom.edges)];
    let mut top_loops = vec![top.edges.clone()];
    for hole in &shape.holes {
        let owner = hole_owner.ok_or_else(|| fail("Missing hole provenance"))?;
        let role = format!("hole/{}", hole.id);
        let center = [value(&hole.center[0])?, value(&hole.center[1])?];
        let r = value(&hole.radius)?;
        if let Some(sink) = &shape.countersink {
            let radius = value(&sink.radius)?;
            let depth = value(&sink.depth)?;
            let floor = &h - &depth;
            let low = b.circle(&center, &r, &q(0));
            let small = b.circle(&center, &r, &floor);
            let high = b.circle(&center, &radius, &h);
            b.cylinder(
                owner,
                &format!("{role}/lower"),
                &center,
                &r,
                (&low, &small),
                true,
            );
            let surface = b.surface(
                owner,
                &format!("{role}/taper"),
                Surface::ConicalFrustum {
                    origin: output(&[center[0].clone(), center[1].clone(), floor]),
                    axis: [0, 0, 1],
                    bottom_radius: r.to_string(),
                    top_radius: radius.to_string(),
                    height: depth.to_string(),
                    inward: true,
                },
            );
            b.wall(&[surface], &small, &high, true);
            bottom_loops.push(low.edges);
            top_loops.push(reverse(&high.edges));
        } else if let Some(bore) = &shape.counterbore {
            let radius = value(&bore.radius)?;
            let floor = &h - value(&bore.depth)?;
            let low = b.circle(&center, &r, &q(0));
            let small = b.circle(&center, &r, &floor);
            let large = b.circle(&center, &radius, &floor);
            let high = b.circle(&center, &radius, &h);
            b.cylinder(
                owner,
                &format!("{role}/lower"),
                &center,
                &r,
                (&low, &small),
                true,
            );
            b.cylinder(
                owner,
                &format!("{role}/upper"),
                &center,
                &radius,
                (&large, &high),
                true,
            );
            b.cap(
                owner,
                &format!("{role}/shoulder"),
                &floor,
                true,
                vec![large.edges.clone(), reverse(&small.edges)],
            );
            bottom_loops.push(low.edges);
            top_loops.push(reverse(&high.edges));
        } else {
            let floor = shape
                .hole_depth
                .as_ref()
                .map(|d| value(d).map(|d| &h - d))
                .transpose()?
                .unwrap_or(q(0));
            let low = b.circle(&center, &r, &floor);
            let high = b.circle(&center, &r, &h);
            b.cylinder(
                owner,
                &format!("{role}/wall"),
                &center,
                &r,
                (&low, &high),
                true,
            );
            if shape.hole_depth.is_some() {
                b.cap(
                    owner,
                    &format!("{role}/floor"),
                    &floor,
                    true,
                    vec![low.edges],
                );
            } else {
                bottom_loops.push(low.edges);
            }
            top_loops.push(reverse(&high.edges));
        }
    }
    b.cap(owner, "cap/bottom", &q(0), false, bottom_loops);
    b.cap(owner, "cap/top", &h, true, top_loops);
    let mut topology = b.topology;
    topology.components = vec![(0..topology.faces.len()).collect()];
    if let Some(frame) = &shape.placement {
        place(&mut topology, frame)?;
    }
    Ok(topology)
}
fn place(topology: &mut Topology, frame: &crate::placement::Placement) -> Result<()> {
    let origin = point(&frame.origin)?;
    let vector =
        |p: &Point| std::array::from_fn(|i| (0..3).map(|j| q(frame.axes[i][j]) * &p[j]).sum());
    let position = |p: &Point| {
        let v: Point = vector(p);
        std::array::from_fn(|i| &v[i] + &origin[i])
    };
    let direction =
        |a: &[i32; 3]| std::array::from_fn(|i| (0..3).map(|j| frame.axes[i][j] * a[j]).sum());
    for p in &mut topology.vertices {
        *p = output(&position(&point(p)?));
    }
    for edge in &mut topology.edges {
        if let Curve::QuarterCircle { center, axis, .. } = &mut edge.curve {
            *center = output(&position(&point(center)?));
            *axis = direction(axis);
        }
    }
    for record in topology.surfaces.values_mut() {
        match &mut record.geometry {
            Surface::Plane { normal, offset } => {
                let n: Point = vector(&point(normal)?);
                *offset = (value(offset)? + dot(&n, &origin)).to_string();
                *normal = output(&n);
            }
            Surface::Cylinder { origin, axis, .. }
            | Surface::ConicalFrustum { origin, axis, .. } => {
                *origin = output(&position(&point(origin)?));
                *axis = direction(axis);
            }
        }
    }
    Ok(())
}
pub(super) fn body(model: &Model, body: &Body) -> Result<Topology> {
    if let Some(shape) = &body.analytic {
        return analytic(model, body, shape);
    }
    let boundary = body
        .boundary
        .as_ref()
        .ok_or_else(|| fail("Missing native boundary"))?;
    let mut result = Builder::new(&body.feature_id, "revision_only").topology;
    result.vertices = boundary.vertices.clone();
    result.edges = boundary
        .edges
        .iter()
        .map(|e| Edge {
            vertices: e.vertices,
            curve: Curve::Line,
        })
        .collect();
    for (i, f) in boundary.faces.iter().enumerate() {
        let id = format!("evaluated/face/{i}");
        result.surfaces.insert(
            id.clone(),
            SurfaceRecord {
                owner_feature: body.feature_id.clone(),
                geometry: Surface::Plane {
                    normal: f.normal.clone(),
                    offset: f.offset.clone(),
                },
            },
        );
        result.faces.push(Face {
            id: id.clone(),
            surface: id,
            loops: f
                .loops
                .iter()
                .map(|r| {
                    r.iter()
                        .map(|u| Use {
                            edge: u.edge,
                            forward: u.forward,
                        })
                        .collect()
                })
                .collect(),
        });
    }
    result.components = body
        .components
        .clone()
        .unwrap_or_else(|| vec![(0..result.faces.len()).collect()]);
    Ok(result)
}
