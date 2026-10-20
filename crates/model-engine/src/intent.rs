//! Explicit feature and parameter provenance for human and AI edit planning.
use super::{error, Feature, Model, Relation, Result};
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet};

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Request {
    pub model: Model,
    pub feature_id: String,
}

#[derive(Serialize)]
pub struct FeatureLinks {
    pub id: String,
    pub inputs: Vec<String>,
    pub parameters: Vec<String>,
}

impl Feature {
    pub(crate) fn links(&self) -> FeatureLinks {
        let (inputs, parameters): (Vec<&String>, Vec<&String>) = match self {
            Self::Block {
                width,
                depth,
                height,
                ..
            } => (vec![], vec![width, depth, height]),
            Self::Cylinder {
                x,
                y,
                radius,
                height,
                ..
            } => (vec![], vec![x, y, radius, height]),
            Self::ConicalFrustum {
                x,
                y,
                bottom_radius,
                top_radius,
                height,
                ..
            } => (vec![], vec![x, y, bottom_radius, top_radius, height]),
            Self::PolygonProfile { vertices, .. } | Self::PlanarProfile { vertices, .. } => {
                (vec![], vertices.iter().flat_map(|v| [&v.x, &v.y]).collect())
            }
            Self::Extrude {
                profile, height, ..
            } => (vec![profile], vec![height]),
            Self::StraightSweep {
                profile, offset, ..
            } => (vec![profile], offset.iter().collect()),
            Self::CoaxialIntersection { left, right, .. }
            | Self::CoaxialBoolean { left, right, .. } => (vec![left, right], vec![]),
            Self::Revolve { profile, .. } => (vec![profile], vec![]),
            Self::PlanarLoft {
                bottom,
                top,
                height,
                ..
            } => (vec![bottom, top], vec![height]),
            Self::CornerCut { input, size, .. } => (vec![input], vec![size]),
            Self::PlaneCut { input, offset, .. } | Self::MirrorPlane { input, offset, .. } => {
                (vec![input], vec![offset])
            }
            Self::PlanarShell {
                input, thickness, ..
            } => (vec![input], vec![thickness]),
            Self::LinearPattern { input, step, .. } => (vec![input], step.iter().collect()),
            Self::Translate { input, offset, .. }
            | Self::Instance {
                source: input,
                offset,
                ..
            } => (vec![input], offset.iter().collect()),
            Self::RotateQuarter { input, pivot, .. } => (vec![input], pivot.iter().collect()),
            Self::Intersection { left, right, .. } | Self::Boolean { left, right, .. } => {
                (vec![left, right], vec![])
            }
            Self::ThroughHoles { input, holes, .. } => (
                vec![input],
                holes.iter().flat_map(|h| [&h.x, &h.y, &h.radius]).collect(),
            ),
            Self::CounterboreHoles {
                input,
                depth,
                bore_radius,
                holes,
                ..
            }
            | Self::CountersinkHoles {
                input,
                depth,
                rim_radius: bore_radius,
                holes,
                ..
            } => (
                vec![input],
                [depth, bore_radius]
                    .into_iter()
                    .chain(holes.iter().flat_map(|h| [&h.x, &h.y, &h.radius]))
                    .collect(),
            ),
            Self::BlindHoles {
                input,
                depth,
                depth_overrides,
                holes,
                ..
            } => (
                vec![input],
                std::iter::once(depth)
                    .chain(depth_overrides.values())
                    .chain(holes.iter().flat_map(|h| [&h.x, &h.y, &h.radius]))
                    .collect(),
            ),
        };
        FeatureLinks {
            id: self.id().into(),
            inputs: inputs
                .into_iter()
                .cloned()
                .collect::<BTreeSet<_>>()
                .into_iter()
                .collect(),
            parameters: parameters
                .into_iter()
                .cloned()
                .collect::<BTreeSet<_>>()
                .into_iter()
                .collect(),
        }
    }
}

#[derive(Serialize)]
pub struct ParameterIntent {
    pub value_mm: String,
    pub directly_editable: bool,
    pub fixed_mm: Option<String>,
    pub relation: Option<Relation>,
    pub driving_parameters: Vec<String>,
    pub affected_parameters: Vec<String>,
    pub affected_features: Vec<String>,
    pub affected_bodies: Vec<String>,
}

#[derive(Serialize)]
pub struct Explanation {
    pub feature_id: String,
    pub terminal_body: bool,
    pub source_features: Vec<FeatureLinks>,
    pub downstream_features: Vec<String>,
    pub parameters: BTreeMap<String, ParameterIntent>,
}

// All graphs have already passed bounded engine validation. Fixed-point walks
// preserve declaration order for features and stable sorted parameter IDs.
fn parameter_closure(model: &Model, initial: BTreeSet<String>, upstream: bool) -> BTreeSet<String> {
    let mut result = initial;
    loop {
        let before = result.len();
        for (id, relation) in &model.relations {
            if upstream && result.contains(id) {
                result.extend(relation.terms.keys().cloned());
            } else if !upstream && relation.terms.keys().any(|p| result.contains(p)) {
                result.insert(id.clone());
            }
        }
        if result.len() == before {
            return result;
        }
    }
}

pub fn explain(request: Request) -> Result<Explanation> {
    let evaluated = super::evaluate(super::Request {
        schema_version: 1,
        model: request.model,
        operations: vec![],
        preserve: vec![],
    })?;
    let model = evaluated.model;
    let links: Vec<_> = model.features.iter().map(Feature::links).collect();
    if !links.iter().any(|f| f.id == request.feature_id) {
        return Err(error(
            "missing_feature",
            &request.feature_id,
            "Feature does not exist",
        ));
    }
    let terminal: BTreeSet<_> = evaluated.bodies.into_iter().map(|b| b.feature_id).collect();
    let mut ancestors = BTreeSet::from([request.feature_id.clone()]);
    for feature in links.iter().rev() {
        if ancestors.contains(&feature.id) {
            ancestors.extend(feature.inputs.iter().cloned());
        }
    }
    let mut downstream = BTreeSet::from([request.feature_id.clone()]);
    for feature in &links {
        if feature.inputs.iter().any(|id| downstream.contains(id)) {
            downstream.insert(feature.id.clone());
        }
    }
    let relevant = parameter_closure(
        &model,
        links
            .iter()
            .filter(|f| ancestors.contains(&f.id))
            .flat_map(|f| f.parameters.iter().cloned())
            .collect(),
        true,
    );
    let parameters = relevant
        .into_iter()
        .map(|id| {
            let driving = parameter_closure(&model, BTreeSet::from([id.clone()]), true);
            let affected = parameter_closure(&model, BTreeSet::from([id.clone()]), false);
            let mut affected_features = BTreeSet::new();
            for feature in &links {
                if feature.parameters.iter().any(|p| affected.contains(p))
                    || feature.inputs.iter().any(|f| affected_features.contains(f))
                {
                    affected_features.insert(feature.id.clone());
                }
            }
            let intent = ParameterIntent {
                value_mm: model.parameters[&id].clone(),
                directly_editable: !model.fixed.contains_key(&id)
                    && !model.relations.contains_key(&id),
                fixed_mm: model.fixed.get(&id).cloned(),
                relation: model.relations.get(&id).cloned(),
                driving_parameters: driving
                    .into_iter()
                    .filter(|p| p != &id && !model.relations.contains_key(p))
                    .collect(),
                affected_parameters: affected.into_iter().filter(|p| p != &id).collect(),
                affected_bodies: affected_features.intersection(&terminal).cloned().collect(),
                affected_features: links
                    .iter()
                    .filter(|f| affected_features.contains(&f.id))
                    .map(|f| f.id.clone())
                    .collect(),
            };
            (id, intent)
        })
        .collect();
    Ok(Explanation {
        feature_id: request.feature_id.clone(),
        terminal_body: terminal.contains(&request.feature_id),
        downstream_features: links
            .iter()
            .filter(|f| f.id != request.feature_id && downstream.contains(&f.id))
            .map(|f| f.id.clone())
            .collect(),
        source_features: links
            .into_iter()
            .filter(|f| ancestors.contains(&f.id))
            .collect(),
        parameters,
    })
}
