//! AI and human edits use the same bounded, deterministic model evaluator.
#![forbid(unsafe_code)]
use boundary_clip::{Boundary, Edge, Face, Plane, Request as ClipRequest, Use};
use num_bigint::BigInt;
use num_rational::BigRational as Q;
use num_traits::{Signed, Zero};
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet};
mod holes;
pub mod mesh;
mod profile;
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
    Cylinder {
        id: String,
        x: String,
        y: String,
        radius: String,
        height: String,
    },
    BlindHoles {
        id: String,
        input: String,
        depth: String,
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
            | Self::ThroughHoles { id, .. }
            | Self::Cylinder { id, .. }
            | Self::BlindHoles { id, .. } => id,
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
pub fn validate(m: &Model) -> Result<Vec<Body>> {
    Ok(evaluate_geometry(m)?.0)
}
fn evaluate_geometry(m: &Model) -> Result<(Vec<Body>, Vec<EvaluatedProfile>)> {
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
    let mut evaluated = BTreeMap::new();
    let mut profiles = BTreeMap::new();
    let mut consumed = BTreeSet::new();
    let mut ids = BTreeSet::new();
    for feature in &m.features {
        let id = feature.id();
        identifier(id)?;
        if !ids.insert(id) {
            return Err(error("duplicate_id", id, "Feature ID already exists"));
        }
        let (boundary, plane) = match feature {
            Feature::ThroughHoles { input, holes, .. }
            | Feature::BlindHoles { input, holes, .. } => {
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
                let shape = if let Feature::BlindHoles { depth, .. } = feature {
                    holes::blind(m, id, depth, shape)?
                } else {
                    shape
                };
                if !consumed.insert(input.as_str()) {
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
                    id,
                    Body {
                        feature_id: id.into(),
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
                    id,
                    Body {
                        feature_id: id.into(),
                        boundary: None,
                        analytic: Some(shape),
                        volume_mm3,
                    },
                );
                continue;
            }
            Feature::PlanarProfile { vertices, .. } => {
                profiles.insert(id, profile::resolve_planar(m, id, vertices)?);
                continue;
            }
            Feature::PolygonProfile { vertices, .. } => {
                profiles.insert(id, profile::resolve(m, id, vertices)?);
                continue;
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
                        id,
                        Body {
                            feature_id: id.into(),
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
                if !consumed.insert(input.as_str()) {
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
        evaluated.insert(
            id,
            Body {
                feature_id: id.into(),
                boundary: Some(result.boundary),
                analytic: None,
                volume_mm3: result.volume,
            },
        );
    }
    let bodies = evaluated
        .into_iter()
        .filter(|(id, _)| !consumed.contains(id))
        .map(|(_, v)| v)
        .collect();
    Ok((bodies, profiles.into_values().map(|p| p.output()).collect()))
}
pub fn evaluate(request: Request) -> Result<Evaluation> {
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
    validate(&request.model)?;
    let before = request.model;
    let mut model = before.clone();
    for op in request.operations {
        match op {
            Operation::DefineParameter { id, mm } => {
                identifier(&id)?;
                if model.parameters.contains_key(&id) {
                    return Err(error("duplicate_id", &id, "Parameter already exists"));
                }
                let n = rational(&mm, &id)?;
                model.parameters.insert(id, n.to_string());
            }
            Operation::SetParameter { id, mm } => {
                relations::require_free(&model, &id)?;
                parameter(&model, &id)?;
                let n = rational(&mm, &id)?;
                model.parameters.insert(id, n.to_string());
            }
            Operation::AdjustParameter { id, delta_mm } => {
                relations::require_free(&model, &id)?;
                let n = parameter(&model, &id)? + rational(&delta_mm, &id)?;
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
    let (bodies, profiles) = evaluate_geometry(&model)?;
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
