//! AI and human edits use the same bounded, deterministic model evaluator.
#![forbid(unsafe_code)]
use boundary_clip::{Boundary, Edge, Face, Plane, Request as ClipRequest, Use};
use num_bigint::BigInt;
use num_rational::BigRational as Q;
use num_traits::{Signed, Zero};
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet};
pub mod clearance;
mod dimension;
pub mod edge_measure;
mod holes;
pub mod intent;
pub mod interference;
pub mod measure;
mod measure_curved;
pub mod mesh;
mod mesh_counterbore;
mod pattern;
pub mod polyhedral;
mod rebuild;
mod revolution;
mod shell;
mod sweep;
pub mod topology;
pub use polyhedral::Operation as BooleanOperation;
pub mod placement;
mod profile;
mod solid_ops;
pub use holes::{AnalyticPrism, Hole};
mod relations;
pub use profile::{EvaluatedProfile, ProfileVertex};
pub use relations::Relation;

#[derive(Debug, Serialize)]
pub struct Error {
    pub code: &'static str,
    pub entity: String,
    pub message: String,
}
type Result<T> = std::result::Result<T, Error>;
fn error(code: &'static str, entity: &str, message: &str) -> Error {
    Error {
        code,
        entity: entity.into(),
        message: message.into(),
    }
}
#[derive(Clone, Debug, Default, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Model {
    pub parameters: BTreeMap<String, String>,
    pub features: Vec<Feature>,
    pub fixed: BTreeMap<String, String>,
    #[serde(default, skip_serializing_if = "BTreeMap::is_empty")]
    pub relations: BTreeMap<String, Relation>,
}
#[derive(Clone, Copy, Debug, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Axis {
    X,
    Y,
    Z,
}
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
pub enum Feature {
    /// One strictly convex loop on the XY plane, with parameter-backed coordinates.
    PolygonProfile {
        id: String,
        vertices: Vec<ProfileVertex>,
    },
    /// One simple planar polygon, including concave outlines.
    PlanarProfile {
        id: String,
        vertices: Vec<ProfileVertex>,
    },
    /// A positive-Z extrusion of an earlier profile; height references a parameter.
    Extrude {
        id: String,
        profile: String,
        height: String,
    },
    /// Straight translation of a planar profile along an exact XYZ displacement.
    StraightSweep {
        id: String,
        profile: String,
        offset: [String; 3],
    },
    /// Full turn about Z: source profile X is radius and Y is axial Z.
    Revolve { id: String, profile: String },
    /// Join matching convex XY profiles at z=0 and z=height with planar sides.
    PlanarLoft {
        id: String,
        bottom: String,
        top: String,
        height: String,
    },
    Cylinder {
        id: String,
        x: String,
        y: String,
        radius: String,
        height: String,
    },
    ConicalFrustum {
        id: String,
        x: String,
        y: String,
        bottom_radius: String,
        top_radius: String,
        height: String,
    },
    /// Keep the closed half-space normal dot position <= offset.
    PlaneCut {
        id: String,
        input: String,
        normal: [String; 3],
        offset: String,
    },
    /// Hollow convex planar stock with exact inward wall thickness.
    PlanarShell {
        id: String,
        input: String,
        thickness: String,
        #[serde(default, skip_serializing_if = "Option::is_none")]
        opening_normal: Option<[String; 3]>,
    },
    /// Repeated planar material, including the original, combined as an exact union.
    LinearPattern {
        id: String,
        input: String,
        count: usize,
        step: [String; 3],
    },
    /// Exact reflection across a rational plane, optionally retaining the source.
    MirrorPlane {
        id: String,
        input: String,
        normal: [String; 3],
        offset: String,
        #[serde(default)]
        keep_original: bool,
    },
    /// Exact right-handed quarter turns about a parameter-backed pivot.
    RotateQuarter {
        id: String,
        input: String,
        axis: Axis,
        turns: i32,
        pivot: [String; 3],
    },
    /// Exact XYZ translation of an earlier convex planar solid.
    Translate {
        id: String,
        input: String,
        offset: [String; 3],
    },
    /// A linked, non-consuming translated placement of an earlier planar solid.
    Instance {
        id: String,
        source: String,
        offset: [String; 3],
    },
    /// Original exact planar Boolean with merged faces, holes and components.
    Boolean {
        id: String,
        left: String,
        right: String,
        operation: BooleanOperation,
    },
    /// Keep the common volume of two earlier convex planar solids.
    Intersection {
        id: String,
        left: String,
        right: String,
    },
    BlindHoles {
        id: String,
        input: String,
        depth: String,
        #[serde(default, skip_serializing_if = "BTreeMap::is_empty")]
        depth_overrides: BTreeMap<String, String>,
        holes: Vec<Hole>,
    },
    CountersinkHoles {
        id: String,
        input: String,
        depth: String,
        rim_radius: String,
        holes: Vec<Hole>,
    },
    CounterboreHoles {
        id: String,
        input: String,
        depth: String,
        bore_radius: String,
        holes: Vec<Hole>,
    },
    ThroughHoles {
        id: String,
        input: String,
        holes: Vec<Hole>,
    },
    Block {
        id: String,
        width: String,
        depth: String,
        height: String,
    },
    /// Removes the +X/+Y vertical corner; size is the setback along each edge.
    CornerCut {
        id: String,
        input: String,
        size: String,
    },
}
impl Feature {
    fn id(&self) -> &str {
        match self {
            Self::Block { id, .. }
            | Self::CornerCut { id, .. }
            | Self::PolygonProfile { id, .. }
            | Self::PlanarProfile { id, .. }
            | Self::Extrude { id, .. }
            | Self::PlanarLoft { id, .. }
            | Self::ThroughHoles { id, .. }
            | Self::Cylinder { id, .. }
            | Self::ConicalFrustum { id, .. }
            | Self::Revolve { id, .. }
            | Self::StraightSweep { id, .. }
            | Self::BlindHoles { id, .. }
            | Self::CounterboreHoles { id, .. }
            | Self::CountersinkHoles { id, .. }
            | Self::PlaneCut { id, .. }
            | Self::PlanarShell { id, .. }
            | Self::LinearPattern { id, .. }
            | Self::MirrorPlane { id, .. }
            | Self::Intersection { id, .. }
            | Self::Translate { id, .. }
            | Self::Instance { id, .. }
            | Self::RotateQuarter { id, .. }
            | Self::Boolean { id, .. } => id,
        }
    }
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(tag = "op", rename_all = "snake_case", deny_unknown_fields)]
pub enum Operation {
    DefineParameter { id: String, mm: String },
    SetParameter { id: String, mm: String },
    AdjustParameter { id: String, delta_mm: String },
    AddFeature { feature: Feature },
    ReplaceFeature { id: String, feature: Feature },
    RemoveFeature { id: String },
    RemoveParameter { id: String },
    FixParameter { id: String },
    ReleaseParameter { id: String },
    SetRelation { id: String, relation: Relation },
    RemoveRelation { id: String },
}
#[derive(Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Request {
    pub schema_version: u32,
    pub model: Model,
    pub operations: Vec<Operation>,
    /// Preconditions: these parameters must retain their prior exact values.
    pub preserve: Vec<String>,
}
#[derive(Debug, Serialize)]
pub struct Body {
    pub feature_id: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub components: Option<Vec<Vec<usize>>>,
    #[serde(skip)]
    pub(crate) polyhedral: Option<polyhedral::Solid>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub boundary: Option<Boundary>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub analytic: Option<AnalyticPrism>,
    pub volume_mm3: String,
}
#[derive(Debug, Serialize)]
pub struct Evaluation {
    pub schema_version: u32,
    pub units: &'static str,
    pub model: Model,
    pub bodies: Vec<Body>,
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub profiles: Vec<EvaluatedProfile>,
    pub changed_parameters: Vec<String>,
}
fn identifier(s: &str) -> Result<()> {
    if s.is_empty()
        || s.len() > 64
        || !s
            .bytes()
            .all(|c| c.is_ascii_alphanumeric() || b"_.-".contains(&c))
    {
        return Err(error(
            "invalid_id",
            s,
            "IDs must be 1..64 ASCII letters, digits, _, . or -",
        ));
    }
    Ok(())
}
fn rational(s: &str, id: &str) -> Result<Q> {
    let invalid = || {
        error(
            "invalid_number",
            id,
            "Use an integer or integer/fraction string, at most 128 bits per component",
        )
    };
    if s.len() > 80 {
        return Err(invalid());
    }
    let (a, b) = s.split_once('/').unwrap_or((s, "1"));
    let integer = |v: &str| -> Result<BigInt> {
        let digits = v.strip_prefix('-').unwrap_or(v);
        if digits.is_empty() || !digits.bytes().all(|c| c.is_ascii_digit()) {
            return Err(invalid());
        }
        let n: BigInt = v.parse().map_err(|_| invalid())?;
        if n.bits() > 128 {
            return Err(invalid());
        }
        Ok(n)
    };
    let (a, b) = (integer(a)?, integer(b)?);
    if b.is_zero() {
        return Err(invalid());
    }
    Ok(Q::new(a, b))
}
fn parameter(m: &Model, id: &str) -> Result<Q> {
    rational(
        m.parameters
            .get(id)
            .ok_or_else(|| error("missing_parameter", id, "Parameter does not exist"))?,
        id,
    )
}
fn positive(m: &Model, id: &str) -> Result<Q> {
    let n = parameter(m, id)?;
    if !n.is_positive() || n > Q::from_integer(1_000_000.into()) {
        return Err(error(
            "dimension_range",
            id,
            "Dimensions must be > 0 and <= 1000000 mm",
        ));
    }
    Ok(n)
}
fn block(w: &Q, d: &Q, h: &Q) -> Boundary {
    let z = Q::zero();
    let vertices = [
        [&z, &z, &z],
        [&z, d, &z],
        [w, d, &z],
        [w, &z, &z],
        [&z, &z, h],
        [w, &z, h],
        [w, d, h],
        [&z, d, h],
    ]
    .map(|p| p.map(ToString::to_string))
    .to_vec();
    let mut edges = Vec::<Edge>::new();
    let mut faces = Vec::new();
    let mut edge_map = BTreeMap::new();
    for (indices, normal, offset) in [
        ([0, 1, 2, 3], [0, 0, -1], &z),
        ([4, 5, 6, 7], [0, 0, 1], h),
        ([0, 3, 5, 4], [0, -1, 0], &z),
        ([1, 7, 6, 2], [0, 1, 0], d),
        ([0, 4, 7, 1], [-1, 0, 0], &z),
        ([3, 2, 6, 5], [1, 0, 0], w),
    ] {
        let mut uses = Vec::new();
        for i in 0..4 {
            let (a, b) = (indices[i], indices[(i + 1) % 4]);
            let key = [a.min(b), a.max(b)];
            let edge = *edge_map.entry(key).or_insert_with(|| {
                edges.push(Edge {
                    kind: "line".into(),
                    vertices: key,
                });
                edges.len() - 1
            });
            uses.push(Use {
                edge,
                forward: a < b,
            });
        }
        faces.push(Face {
            kind: "plane".into(),
            normal: normal.map(|n| n.to_string()),
            offset: offset.to_string(),
            loops: vec![uses],
        });
    }
    Boundary {
        vertices,
        edges,
        faces,
    }
}
fn polyhedral_body(id: &str, solid: polyhedral::Solid) -> Body {
    Body {
        feature_id: id.into(),
        boundary: Some(solid.boundary.clone()),
        analytic: None,
        volume_mm3: solid.volume.to_string(),
        components: Some(solid.components.clone()),
        polyhedral: Some(solid),
    }
}

// Construct backing cells only when an operation needs a nonconvex profile.
// Keep existing serialized source prisms and convex operation results stable.
fn polyhedral_input(
    m: &Model,
    profiles: &BTreeMap<String, profile::Profile>,
    evaluated: &BTreeMap<String, Body>,
    input: &str,
) -> Result<Option<polyhedral::Solid>> {
    let Some(parent) = evaluated.get(input) else {
        return Ok(None);
    };
    if let Some(solid) = &parent.polyhedral {
        return Ok(Some(solid.clone()));
    }
    if let Some(Feature::Extrude {
        profile, height, ..
    }) = m.features.iter().find(|f| f.id() == input)
    {
        let outline = &profiles[profile.as_str()];
        if !profile::is_convex(outline) {
            return polyhedral::Solid::from_profile(outline, &positive(m, height)?).map(Some);
        }
    }
    Ok(None)
}

// Resolve a bounded planar rigid transform without losing nonconvex backing cells.
fn transformed_body(
    m: &Model,
    profiles: &BTreeMap<String, profile::Profile>,
    evaluated: &BTreeMap<String, Body>,
    id: &str,
    input: &str,
    mut transform: impl FnMut(Boundary) -> Result<Body>,
) -> Result<Body> {
    if let Some(solid) = polyhedral_input(m, profiles, evaluated, input)? {
        let transformed = solid
            .transform(|cell| {
                transform(cell)?.boundary.ok_or_else(|| {
                    error(
                        "invalid_geometry",
                        id,
                        "Planar transform did not return a boundary",
                    )
                })
            })
            .map_err(|mut e| {
                e.entity = id.into();
                e
            })?;
        return Ok(polyhedral_body(id, transformed));
    }
    transform(convex_input(
        m,
        profiles,
        evaluated,
        input,
        "Rigid transforms",
    )?)
}

fn convex_input(
    m: &Model,
    profiles: &BTreeMap<String, profile::Profile>,
    evaluated: &BTreeMap<String, Body>,
    input: &str,
    operation: &str,
) -> Result<Boundary> {
    let parent = evaluated.get(input).ok_or_else(|| {
        error(
            "unsupported_reference",
            input,
            "Operation must reference an earlier convex planar solid",
        )
    })?;
    if let Some(boundary) = &parent.boundary {
        if parent.polyhedral.is_some() {
            // A merged Boolean may still be convex. Validate that property before
            // passing it to an operation whose established contract is convex-only.
            let face = &boundary.faces[0];
            if boundary_clip::clip(ClipRequest {
                schema_version: 1,
                boundary: boundary.clone(),
                plane: Plane {
                    normal: face.normal.clone(),
                    offset: face.offset.clone(),
                },
            })
            .is_err()
            {
                return Err(error("unsupported_reference",input,"This operation requires a convex planar body; this Boolean result is nonconvex or disconnected"));
            }
        }
        return Ok(boundary.clone());
    }
    if let Some(Feature::Extrude {
        profile, height, ..
    }) = m.features.iter().find(|f| f.id() == input)
    {
        // Build a boundary for this operation without changing the source prism.
        return profile::convex_boundary(
            &profiles[profile.as_str()],
            &positive(m, height)?,
            input,
            operation,
        );
    }
    Err(error("unsupported_reference", input, "Operation requires convex unperforated planar stock; circular and perforated stock are unsupported"))
}

pub fn validate(m: &Model) -> Result<Vec<Body>> {
    Ok(evaluate_geometry(m)?.into_parts().0)
}
fn evaluate_geometry(m: &Model) -> Result<rebuild::Geometry> {
    evaluate_geometry_from(m, rebuild::Geometry::default(), 0)
}
fn evaluate_geometry_from(
    m: &Model,
    state: rebuild::Geometry,
    start: usize,
) -> Result<rebuild::Geometry> {
    if m.parameters.len() > 64 || m.features.len() > 32 || m.fixed.len() > 64 {
        return Err(error(
            "model_limit",
            "model",
            "Maximum 64 parameters, 32 features, 64 fixed values",
        ));
    }
    for (id, value) in &m.parameters {
        identifier(id)?;
        rational(value, id)?;
    }
    relations::validate(m)?;
    for (id, value) in &m.fixed {
        if parameter(m, id)? != rational(value, id)? {
            return Err(error(
                "constraint_conflict",
                id,
                "Parameter is fixed; release its constraint explicitly before changing it",
            ));
        }
    }
    let rebuild::Geometry {
        mut evaluated,
        mut profiles,
        mut consumed,
        mut checkpoints,
    } = state;
    let mut ids: BTreeSet<_> = m.features[..start].iter().map(Feature::id).collect();
    for feature in &m.features[start..] {
        checkpoints.push(consumed.clone());
        let id = feature.id();
        identifier(id)?;
        if !ids.insert(id) {
            return Err(error("duplicate_id", id, "Feature ID already exists"));
        }
        let (boundary, plane) = match feature {
            Feature::ThroughHoles { input, holes, .. }
            | Feature::BlindHoles { input, holes, .. }
            | Feature::CounterboreHoles { input, holes, .. }
            | Feature::CountersinkHoles { input, holes, .. } => {
                let parent = m
                    .features
                    .iter()
                    .take_while(|f| f.id() != id)
                    .find(|f| f.id() == input);
                let shape = match parent {
                    Some(Feature::Extrude {
                        profile, height, ..
                    }) => holes::resolve(
                        m,
                        id,
                        &profiles[profile.as_str()],
                        &positive(m, height)?,
                        holes,
                    )?,
                    Some(Feature::Cylinder {
                        x,
                        y,
                        radius,
                        height,
                        ..
                    }) => {
                        holes::resolve_round(m, id, holes::round(m, x, y, radius, height)?, holes)?
                    }
                    _ => {
                        return Err(error(
                            "unsupported_reference",
                            input,
                            "Through holes require an earlier profile extrusion or cylinder",
                        ))
                    }
                };
                let shape = match feature {
                    Feature::BlindHoles {
                        depth,
                        depth_overrides,
                        ..
                    } => holes::blind(m, id, depth, depth_overrides, shape)?,
                    Feature::CounterboreHoles {
                        depth, bore_radius, ..
                    } => holes::recess(m, id, depth, bore_radius, shape, false)?,
                    Feature::CountersinkHoles {
                        depth, rim_radius, ..
                    } => holes::recess(m, id, depth, rim_radius, shape, true)?,
                    _ => shape,
                };
                if !consumed.insert(input.clone()) {
                    return Err(error(
                        "unsupported_branch",
                        input,
                        "Only one hole group per stock feature is supported",
                    ));
                }
                let volume_mm3 = if shape.outer_circle.is_some() {
                    format!(
                        "{}*pi",
                        shape.volume.pi_subtract_mm3.trim_start_matches('-')
                    )
                } else {
                    format!(
                        "{} - ({})*pi",
                        shape.volume.constant_mm3, shape.volume.pi_subtract_mm3
                    )
                };
                evaluated.insert(
                    id.into(),
                    Body {
                        feature_id: id.into(),
                        components: None,
                        polyhedral: None,
                        boundary: None,
                        analytic: Some(shape),
                        volume_mm3,
                    },
                );
                continue;
            }
            Feature::PlanarShell {
                input,
                thickness,
                opening_normal,
                ..
            } => {
                if !consumed.insert(input.clone()) {
                    return Err(error(
                        "unsupported_branch",
                        input,
                        "Choose a terminal solid for hollowing",
                    ));
                }
                let outer = convex_input(m, &profiles, &evaluated, input, "Planar shells")?;
                let solid =
                    shell::hollow(id, outer, &positive(m, thickness)?, opening_normal.as_ref())
                        .map_err(|mut e| {
                            e.entity = id.into();
                            e
                        })?;
                evaluated.insert(id.into(), polyhedral_body(id, solid));
                continue;
            }
            Feature::LinearPattern {
                input, count, step, ..
            } => {
                if !consumed.insert(input.clone()) {
                    return Err(error(
                        "unsupported_branch",
                        input,
                        "Choose a terminal solid for a material pattern",
                    ));
                }
                let source = match polyhedral_input(m, &profiles, &evaluated, input)? {
                    Some(solid) => solid,
                    None => polyhedral::Solid::from_convex(convex_input(
                        m,
                        &profiles,
                        &evaluated,
                        input,
                        "Planar patterns",
                    )?)?,
                };
                let delta = [
                    parameter(m, &step[0])?,
                    parameter(m, &step[1])?,
                    parameter(m, &step[2])?,
                ];
                let solid = pattern::linear(id, source, *count, &delta).map_err(|mut e| {
                    e.entity = id.into();
                    e
                })?;
                evaluated.insert(id.into(), polyhedral_body(id, solid));
                continue;
            }
            Feature::Boolean {
                left,
                right,
                operation,
                ..
            } => {
                if left == right {
                    return Err(error(
                        "invalid_operands",
                        id,
                        "Choose two distinct terminal solids",
                    ));
                }
                let resolve = |input: &str| -> Result<polyhedral::Solid> {
                    if let Some(solid) = polyhedral_input(m, &profiles, &evaluated, input)? {
                        return Ok(solid);
                    }
                    polyhedral::Solid::from_convex(convex_input(
                        m,
                        &profiles,
                        &evaluated,
                        input,
                        "Planar Booleans",
                    )?)
                };
                let a = resolve(left)?;
                let b = resolve(right)?;
                for input in [left, right] {
                    if !consumed.insert(input.clone()) {
                        return Err(error(
                            "unsupported_branch",
                            input,
                            "Choose terminal solids; an input can have only one consuming feature",
                        ));
                    }
                }
                let solid = a.combine(&b, *operation).map_err(|mut e| {
                    e.entity = id.into();
                    e
                })?;
                evaluated.insert(id.into(), polyhedral_body(id, solid));
                continue;
            }
            Feature::MirrorPlane {
                input,
                normal,
                offset,
                keep_original,
                ..
            } => {
                if !keep_original && !consumed.insert(input.clone()) {
                    return Err(error(
                        "unsupported_branch",
                        input,
                        "Choose a terminal source when replacing it with its mirror",
                    ));
                }
                let normal = [
                    rational(&normal[0], id)?,
                    rational(&normal[1], id)?,
                    rational(&normal[2], id)?,
                ];
                let offset = parameter(m, offset)?;
                let body = transformed_body(m, &profiles, &evaluated, id, input, |boundary| {
                    solid_ops::mirror(id, boundary, &normal, &offset)
                })?;
                evaluated.insert(id.into(), body);
                continue;
            }
            Feature::RotateQuarter {
                input,
                axis,
                turns,
                pivot,
                ..
            } => {
                if !(1..=3).contains(turns) {
                    return Err(error(
                        "rotation_range",
                        id,
                        "Quarter turns must be 1, 2 or 3 (90, 180 or 270 degrees)",
                    ));
                }
                if !consumed.insert(input.clone()) {
                    return Err(error(
                        "unsupported_branch",
                        input,
                        "A solid can have only one consuming feature; select a terminal result",
                    ));
                }
                let origin = [
                    parameter(m, &pivot[0])?,
                    parameter(m, &pivot[1])?,
                    parameter(m, &pivot[2])?,
                ];
                if origin
                    .iter()
                    .any(|q| q.abs() > Q::from_integer(1_000_000.into()))
                {
                    return Err(error(
                        "rotation_range",
                        id,
                        "Pivot coordinates must be within +/-1000000 mm",
                    ));
                }
                let rotated = placement::rotate(origin.clone(), *axis, *turns);
                let delta = std::array::from_fn(|i| &origin[i] - &rotated[i]);
                let analytic = evaluated
                    .get(input.as_str())
                    .map(|body| placement::analytic(body, id, &delta, Some((*axis, *turns))))
                    .transpose()?
                    .flatten();
                let body = match analytic {
                    Some(body) => body,
                    None => transformed_body(m, &profiles, &evaluated, id, input, |boundary| {
                        solid_ops::rotate_quarter(id, boundary, *axis, *turns, &origin)
                    })?,
                };
                evaluated.insert(id.into(), body);
                continue;
            }
            Feature::Translate { input, offset, .. }
            | Feature::Instance {
                source: input,
                offset,
                ..
            } => {
                if matches!(feature, Feature::Translate { .. }) && !consumed.insert(input.clone()) {
                    return Err(error(
                        "unsupported_branch",
                        input,
                        "A solid can have only one consuming feature; select a terminal result",
                    ));
                }
                let delta = [
                    parameter(m, &offset[0])?,
                    parameter(m, &offset[1])?,
                    parameter(m, &offset[2])?,
                ];
                if delta
                    .iter()
                    .any(|q| q.abs() > Q::from_integer(1_000_000.into()))
                {
                    return Err(error(
                        "translation_range",
                        id,
                        "Each translation component must be within +/-1000000 mm",
                    ));
                }
                let analytic = evaluated
                    .get(input.as_str())
                    .map(|body| placement::analytic(body, id, &delta, None))
                    .transpose()?
                    .flatten();
                let body = match analytic {
                    Some(body) => body,
                    None => transformed_body(m, &profiles, &evaluated, id, input, |boundary| {
                        solid_ops::translate(id, boundary, &delta)
                    })?,
                };
                evaluated.insert(id.into(), body);
                continue;
            }
            Feature::Intersection { left, right, .. } => {
                if left == right {
                    return Err(error(
                        "invalid_intersection",
                        id,
                        "Select two distinct input features",
                    ));
                }
                let a = convex_input(m, &profiles, &evaluated, left, "Intersections")?;
                let b = convex_input(m, &profiles, &evaluated, right, "Intersections")?;
                for input in [left, right] {
                    if !consumed.insert(input.clone()) {
                        return Err(error(
                            "unsupported_branch",
                            input,
                            "A solid can have only one consuming feature; select a terminal result",
                        ));
                    }
                }
                evaluated.insert(id.into(), solid_ops::intersection(id, a, &b)?);
                continue;
            }
            Feature::StraightSweep {
                profile, offset, ..
            } => {
                let input = profiles.get(profile.as_str()).ok_or_else(|| {
                    error(
                        "unsupported_reference",
                        profile,
                        "Sweep must reference an earlier polygon profile",
                    )
                })?;
                let delta = [
                    parameter(m, &offset[0])?,
                    parameter(m, &offset[1])?,
                    parameter(m, &offset[2])?,
                ];
                let solid = polyhedral::Solid::from_sweep(id, input, &delta)?;
                evaluated.insert(id.into(), polyhedral_body(id, solid));
                continue;
            }
            Feature::Revolve { profile, .. } => {
                let input = profiles.get(profile.as_str()).ok_or_else(|| {
                    error(
                        "unsupported_reference",
                        profile,
                        "Revolution must reference an earlier polygon profile",
                    )
                })?;
                let shape = revolution::resolve(id, input)?;
                let volume_mm3 = format!(
                    "{}*pi",
                    shape.volume.pi_subtract_mm3.trim_start_matches('-')
                );
                evaluated.insert(
                    id.into(),
                    Body {
                        feature_id: id.into(),
                        components: None,
                        polyhedral: None,
                        boundary: None,
                        analytic: Some(shape),
                        volume_mm3,
                    },
                );
                continue;
            }
            Feature::ConicalFrustum {
                x,
                y,
                bottom_radius,
                top_radius,
                height,
                ..
            } => {
                let shape = holes::frustum(m, x, y, bottom_radius, top_radius, height)?;
                let volume_mm3 = format!(
                    "{}*pi",
                    shape.volume.pi_subtract_mm3.trim_start_matches('-')
                );
                evaluated.insert(
                    id.into(),
                    Body {
                        feature_id: id.into(),
                        components: None,
                        polyhedral: None,
                        boundary: None,
                        analytic: Some(shape),
                        volume_mm3,
                    },
                );
                continue;
            }
            Feature::Cylinder {
                x,
                y,
                radius,
                height,
                ..
            } => {
                let shape = holes::round(m, x, y, radius, height)?;
                let volume_mm3 = format!(
                    "{}*pi",
                    shape.volume.pi_subtract_mm3.trim_start_matches('-')
                );
                evaluated.insert(
                    id.into(),
                    Body {
                        feature_id: id.into(),
                        components: None,
                        polyhedral: None,
                        boundary: None,
                        analytic: Some(shape),
                        volume_mm3,
                    },
                );
                continue;
            }
            Feature::PlanarProfile { vertices, .. } => {
                profiles.insert(id.into(), profile::resolve_planar(m, id, vertices)?);
                continue;
            }
            Feature::PolygonProfile { vertices, .. } => {
                profiles.insert(id.into(), profile::resolve(m, id, vertices)?);
                continue;
            }
            Feature::PlanarLoft {
                bottom,
                top,
                height,
                ..
            } => {
                let get = |reference: &str| {
                    profiles.get(reference).ok_or_else(|| {
                        error(
                            "unsupported_reference",
                            reference,
                            "Loft must reference earlier polygon profiles",
                        )
                    })
                };
                let h = positive(m, height)?;
                (
                    profile::loft(id, get(bottom)?, get(top)?, &h)?,
                    Plane {
                        normal: ["0".into(), "0".into(), "1".into()],
                        offset: h.to_string(),
                    },
                )
            }
            Feature::Extrude {
                profile, height, ..
            } => {
                let input = profiles.get(profile.as_str()).ok_or_else(|| {
                    error(
                        "unsupported_reference",
                        profile,
                        "Extrusion must reference an earlier polygon profile",
                    )
                })?;
                let h = positive(m, height)?;
                if !input.convex_only {
                    let shape = holes::prism(input, &h);
                    let volume_mm3 = shape.volume.constant_mm3.clone();
                    evaluated.insert(
                        id.into(),
                        Body {
                            feature_id: id.into(),
                            components: None,
                            polyhedral: None,
                            boundary: None,
                            analytic: Some(shape),
                            volume_mm3,
                        },
                    );
                    continue;
                }
                (
                    profile::extrude(input, &h),
                    Plane {
                        normal: ["0".into(), "0".into(), "1".into()],
                        offset: h.to_string(),
                    },
                )
            }
            Feature::Block {
                width,
                depth,
                height,
                ..
            } => {
                let (w, d, h) = (
                    positive(m, width)?,
                    positive(m, depth)?,
                    positive(m, height)?,
                );
                (
                    block(&w, &d, &h),
                    Plane {
                        normal: ["0".into(), "0".into(), "1".into()],
                        offset: h.to_string(),
                    },
                )
            }
            Feature::PlaneCut {
                input,
                normal,
                offset,
                ..
            } => {
                if !consumed.insert(input.clone()) {
                    return Err(error("unsupported_branch",input,"A solid can have only one consuming feature; apply further cuts to the previous cut"));
                }
                let parsed = [
                    rational(&normal[0], id)?,
                    rational(&normal[1], id)?,
                    rational(&normal[2], id)?,
                ];
                if parsed.iter().all(Zero::is_zero) {
                    return Err(error("plane_normal", id, "Plane normal must be nonzero"));
                }
                let plane = Plane {
                    normal: parsed.map(|n| n.to_string()),
                    offset: parameter(m, offset)?.to_string(),
                };
                if let Some(solid) = polyhedral_input(m, &profiles, &evaluated, input)? {
                    let result = solid.clipped(&plane).map_err(|mut e| {
                        e.entity = id.into();
                        e
                    })?;
                    evaluated.insert(id.into(), polyhedral_body(id, result));
                    continue;
                }
                (
                    convex_input(m, &profiles, &evaluated, input, "Plane cuts")?,
                    plane,
                )
            }
            Feature::CornerCut { input, size, .. } => {
                let parent = m
                    .features
                    .iter()
                    .take_while(|f| f.id() != id)
                    .find(|f| f.id() == input);
                let Some(Feature::Block { width, depth, .. }) = parent else {
                    return Err(error(
                        "unsupported_reference",
                        input,
                        "Corner cut must reference an earlier block feature",
                    ));
                };
                if !consumed.insert(input.clone()) {
                    return Err(error(
                        "unsupported_branch",
                        input,
                        "Only one corner cut per block is supported",
                    ));
                }
                let (w, d, s) = (positive(m, width)?, positive(m, depth)?, positive(m, size)?);
                if s >= w || s >= d {
                    return Err(error(
                        "cut_range",
                        size,
                        "Corner setback must be smaller than width and depth",
                    ));
                }
                let parent: &Body = evaluated.get(input.as_str()).ok_or_else(|| {
                    error("missing_feature", input, "Input has not been evaluated")
                })?;
                (
                    parent
                        .boundary
                        .clone()
                        .expect("earlier block has planar boundary"),
                    Plane {
                        normal: ["1".into(), "1".into(), "0".into()],
                        offset: (w + d - s).to_string(),
                    },
                )
            }
        };
        // Planar solids pass the convex closed-boundary validator.
        // Perforated prisms use exact containment/separation in holes::resolve.
        let result = boundary_clip::clip(ClipRequest {
            schema_version: 1,
            boundary,
            plane,
        })
        .map_err(|message| error("invalid_geometry", id, &message))?;
        if result.classification == "empty" {
            return Err(error("empty_solid", id, "Cut removes the entire solid or leaves only a face/edge/point; adjust the plane or remove the feature explicitly"));
        }
        evaluated.insert(
            id.into(),
            Body {
                feature_id: id.into(),
                components: None,
                polyhedral: None,
                boundary: Some(result.boundary),
                analytic: None,
                volume_mm3: result.volume,
            },
        );
    }
    checkpoints.push(consumed.clone());
    Ok(rebuild::Geometry {
        evaluated,
        profiles,
        consumed,
        checkpoints,
    })
}
pub fn evaluate(request: Request) -> Result<Evaluation> {
    evaluate_with_reuse(request, true)
}
fn evaluate_with_reuse(request: Request, reuse: bool) -> Result<Evaluation> {
    if request.schema_version != 1 {
        return Err(error(
            "schema_version",
            "request",
            "Only version 1 is supported",
        ));
    }
    if request.operations.len() > 128 || request.preserve.len() > 64 {
        return Err(error(
            "request_limit",
            "request",
            "Too many operations or preserve entries",
        ));
    }
    let previous = evaluate_geometry(&request.model)?;
    let before = request.model;
    let mut model = before.clone();
    for op in request.operations {
        match op {
            Operation::DefineParameter { id, mm } => {
                identifier(&id)?;
                if model.parameters.contains_key(&id) {
                    return Err(error("duplicate_id", &id, "Parameter already exists"));
                }
                let n = dimension::parse(&mm, &id)?;
                model.parameters.insert(id, n.to_string());
            }
            Operation::SetParameter { id, mm } => {
                relations::require_free(&model, &id)?;
                parameter(&model, &id)?;
                let n = dimension::parse(&mm, &id)?;
                model.parameters.insert(id, n.to_string());
            }
            Operation::AdjustParameter { id, delta_mm } => {
                relations::require_free(&model, &id)?;
                let n = parameter(&model, &id)? + dimension::parse(&delta_mm, &id)?;
                let value = n.to_string();
                rational(&value, &id)?;
                model.parameters.insert(id, value);
            }
            Operation::AddFeature { feature } => {
                identifier(feature.id())?;
                if model.features.iter().any(|f| f.id() == feature.id()) {
                    return Err(error(
                        "duplicate_id",
                        feature.id(),
                        "Feature ID already exists",
                    ));
                }
                model.features.push(feature);
            }
            Operation::ReplaceFeature { id, feature } => {
                let existing = model
                    .features
                    .iter_mut()
                    .find(|f| f.id() == id)
                    .ok_or_else(|| error("missing_feature", &id, "Feature does not exist"))?;
                if feature.id() != id
                    || std::mem::discriminant(existing) != std::mem::discriminant(&feature)
                {
                    return Err(error(
                        "feature_identity",
                        &id,
                        "Replacement must retain the feature ID and kind",
                    ));
                }
                *existing = feature;
            }
            Operation::RemoveFeature { id } => {
                let index = model
                    .features
                    .iter()
                    .position(|f| f.id() == id)
                    .ok_or_else(|| error("missing_feature", &id, "Feature does not exist"))?;
                model.features.remove(index);
                // Dependency validity is checked after the whole atomic batch,
                // permitting explicit dependent removals in either order.
            }
            Operation::RemoveParameter { id } => {
                parameter(&model, &id)?;
                if model.fixed.contains_key(&id) || model.relations.contains_key(&id) {
                    return Err(error("parameter_in_use", &id, "Release fixed constraints and remove the parameter's relation before deleting it"));
                }
                model.parameters.remove(&id);
                // Geometry and remaining relations must still resolve at commit.
            }
            Operation::FixParameter { id } => {
                relations::refresh(&mut model)?;
                let n = parameter(&model, &id)?;
                model.fixed.entry(id).or_insert_with(|| n.to_string());
            }
            Operation::ReleaseParameter { id } => {
                if model.fixed.remove(&id).is_none() {
                    return Err(error(
                        "missing_constraint",
                        &id,
                        "No fixed constraint exists",
                    ));
                }
            }
            Operation::SetRelation { id, relation } => {
                parameter(&model, &id)?;
                model.relations.insert(id, relation);
            }
            Operation::RemoveRelation { id } => {
                if !model.relations.contains_key(&id) {
                    return Err(error(
                        "missing_relation",
                        &id,
                        "Parameter has no relationship",
                    ));
                }
                // Removing a relationship freezes its current computed value.
                relations::refresh(&mut model)?;
                model.relations.remove(&id);
            }
        }
    }
    relations::refresh(&mut model)?;
    for id in request.preserve {
        if parameter(&before, &id)? != parameter(&model, &id)? {
            return Err(error(
                "preserve_conflict",
                &id,
                "Edit changes a parameter listed in preserve",
            ));
        }
    }
    // A fixed value can only change if explicitly released in the transaction.
    // Re-fixing without releasing must not overwrite an existing invariant.
    let next = if reuse {
        let (state, start) = previous.retain_prefix(&before, &model);
        evaluate_geometry_from(&model, state, start)?
    } else {
        evaluate_geometry(&model)?
    };
    let (bodies, profiles) = next.into_parts();
    let changed_parameters = before
        .parameters
        .keys()
        .chain(model.parameters.keys())
        .collect::<BTreeSet<_>>()
        .into_iter()
        .filter(|id| before.parameters.get(*id) != model.parameters.get(*id))
        .cloned()
        .collect();
    Ok(Evaluation {
        schema_version: 1,
        units: "mm",
        model,
        bodies,
        profiles,
        changed_parameters,
    })
}
