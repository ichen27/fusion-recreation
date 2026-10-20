//! Persistent feature material overrides and deterministic solid ancestry resolution.
use crate::{error, rational, BooleanOperation, Feature, Model, Result};
use num_traits::Signed;
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet};

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Material {
    pub name: String,
    pub density_kg_per_m3: String,
}
impl Material {
    pub(crate) fn normalized(&self, id: &str) -> Result<Self> {
        if self.name.is_empty()
            || self.name.chars().count() > 80
            || self.name.trim() != self.name
            || self.name.chars().any(char::is_control)
        {
            return Err(error("invalid_material", id, "Material name must be1..80 characters, without control characters or outer whitespace"));
        }
        let density = rational(&self.density_kg_per_m3, id)?;
        if !density.is_positive() {
            return Err(error(
                "invalid_density",
                id,
                "Material density must be positive kg/m³",
            ));
        }
        Ok(Self {
            name: self.name.clone(),
            density_kg_per_m3: density.to_string(),
        })
    }
}
#[derive(Clone, Debug, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Status {
    Assigned,
    Unassigned,
    Conflict,
}
#[derive(Clone, Debug, PartialEq, Serialize)]
pub struct Resolved {
    pub status: Status,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub material: Option<Material>,
    pub source_features: Vec<String>,
}
impl Resolved {
    fn unassigned() -> Self {
        Self {
            status: Status::Unassigned,
            material: None,
            source_features: vec![],
        }
    }
}
pub(crate) fn validate(model: &Model) -> Result<()> {
    if model.materials.len() > 32 {
        return Err(error(
            "model_limit",
            "materials",
            "At most32 feature material overrides",
        ));
    }
    for (id, material) in &model.materials {
        material.normalized(id)?;
        let feature = model
            .features
            .iter()
            .find(|f| f.id() == id)
            .ok_or_else(|| {
                error(
                    "missing_feature",
                    id,
                    "Clear this material override before removing its feature",
                )
            })?;
        if matches!(
            feature,
            Feature::PolygonProfile { .. } | Feature::PlanarProfile { .. }
        ) {
            return Err(error(
                "unsupported_material",
                id,
                "Assign materials to solid features, not sketches",
            ));
        }
    }
    Ok(())
}

/// Geometry must have validated the feature dependency graph before this call.
/// Unary operations/copies inherit. Difference takes target material only.
/// Other combinations need equal assigned names/densities on every input.
/// A direct override resolves ambiguity without pretending to preserve mixed regions.
pub(crate) fn resolve(model: &Model) -> Result<BTreeMap<String, Resolved>> {
    let mut states: BTreeMap<String, Resolved> = BTreeMap::new();
    for feature in &model.features {
        let id = feature.id();
        let state = if let Some(material) = model.materials.get(id) {
            Resolved {
                status: Status::Assigned,
                material: Some(material.normalized(id)?),
                source_features: vec![id.into()],
            }
        } else {
            let inputs = match feature {
                Feature::Boolean {
                    left,
                    operation: BooleanOperation::Difference,
                    ..
                }
                | Feature::CoaxialBoolean {
                    left,
                    operation: BooleanOperation::Difference,
                    ..
                } => vec![left.clone()],
                _ => feature.links().inputs,
            };
            let parents: Vec<_> = inputs.iter().filter_map(|id| states.get(id)).collect();
            if parents.is_empty() || parents.iter().all(|p| p.status == Status::Unassigned) {
                Resolved::unassigned()
            } else if parents
                .iter()
                .all(|p| p.status == Status::Assigned && p.material == parents[0].material)
            {
                Resolved {
                    status: Status::Assigned,
                    material: parents[0].material.clone(),
                    source_features: parents
                        .iter()
                        .flat_map(|p| p.source_features.clone())
                        .collect::<BTreeSet<_>>()
                        .into_iter()
                        .collect(),
                }
            } else {
                Resolved {
                    status: Status::Conflict,
                    material: None,
                    source_features: parents
                        .iter()
                        .flat_map(|p| p.source_features.clone())
                        .collect::<BTreeSet<_>>()
                        .into_iter()
                        .collect(),
                }
            }
        };
        states.insert(id.into(), state);
    }
    Ok(states)
}
