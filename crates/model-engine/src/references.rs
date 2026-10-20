//! Named authored surfaces and connected edge chains, guarded by feature ancestry.
//! No geometric nearest-neighbor matching or revision-only face indices are persisted.
use crate::{error, identifier, topology, Body, Feature, Model, Result};
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet};

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
pub enum Target {
    Surface { surface_id: String },
    EdgeChain { surfaces: [String; 2] },
}
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Reference {
    pub feature_id: String,
    pub target: Target,
    pub ancestry: Vec<Feature>,
}
#[derive(Debug, Serialize)]
pub struct Resolved {
    pub feature_id: String,
    pub target: Target,
    pub face_ids: Vec<String>,
    pub edge_indices: Vec<usize>,
}
fn ancestry(model: &Model, id: &str) -> Result<Vec<Feature>> {
    let mut pending = vec![id.to_owned()];
    let mut found = BTreeSet::new();
    while let Some(id) = pending.pop() {
        if !found.insert(id.clone()) {
            continue;
        }
        if found.len() > 32 {
            return Err(error(
                "reference_limit",
                &id,
                "Reference ancestry exceeds 32 features",
            ));
        }
        let feature = model
            .features
            .iter()
            .find(|f| f.id() == id)
            .ok_or_else(|| {
                error(
                    "missing_feature",
                    &id,
                    "Reference source feature is missing",
                )
            })?;
        pending.extend(feature.links().inputs);
    }
    let mut features: Vec<_> = model
        .features
        .iter()
        .filter(|f| found.contains(f.id()))
        .cloned()
        .collect();
    features.sort_by(|a, b| a.id().cmp(b.id()));
    Ok(features)
}
pub(crate) fn bind(model: &Model, feature_id: String, mut target: Target) -> Result<Reference> {
    identifier(&feature_id)?;
    if let Target::EdgeChain { surfaces } = &mut target {
        surfaces.sort();
    }
    Ok(Reference {
        ancestry: ancestry(model, &feature_id)?,
        feature_id,
        target,
    })
}
pub(crate) fn resolve<'a>(
    model: &Model,
    bodies: impl Iterator<Item = &'a Body>,
) -> Result<BTreeMap<String, Resolved>> {
    if model.references.len() > 16 {
        return Err(error(
            "reference_limit",
            "references",
            "At most 16 named references",
        ));
    }
    let bodies: BTreeMap<_, _> = bodies.map(|b| (b.feature_id.as_str(), b)).collect();
    let mut topologies = BTreeMap::new();
    let mut result = BTreeMap::new();
    for (name, reference) in &model.references {
        identifier(name)?;
        if reference.ancestry != ancestry(model, &reference.feature_id)? {
            return Err(error("reference_changed", name, "Source feature structure changed. Remove this reference or explicitly bind it again after inspecting the changed model"));
        }
        let body = bodies.get(reference.feature_id.as_str()).ok_or_else(|| {
            error(
                "reference_missing",
                name,
                "Referenced body is no longer terminal; remove or explicitly rebind the reference",
            )
        })?;
        if !topologies.contains_key(&reference.feature_id) {
            topologies.insert(
                reference.feature_id.clone(),
                topology::for_body(model, body)?,
            );
        }
        let topology = &topologies[&reference.feature_id];
        if topology.naming != "authored_surfaces" {
            return Err(error("unsupported_reference", name, "Named references require authored surfaces; generated Boolean/cut face indices cannot be retained"));
        }
        let surface_ids: Vec<_> = match &reference.target {
            Target::Surface { surface_id } => vec![surface_id],
            Target::EdgeChain { surfaces } => {
                if surfaces[0] >= surfaces[1] {
                    return Err(error(
                        "invalid_reference",
                        name,
                        "Edge chains require two distinct, sorted authored surface names",
                    ));
                }
                surfaces.iter().collect()
            }
        };
        if surface_ids
            .iter()
            .any(|id| id.len() > 256 || !topology.surfaces.contains_key(*id))
        {
            return Err(error(
                "reference_missing",
                name,
                "An authored surface is absent; no replacement was guessed",
            ));
        }
        let face_ids = topology
            .faces
            .iter()
            .filter(|f| surface_ids.contains(&&f.surface))
            .map(|f| f.id.clone())
            .collect();
        let mut edge_indices = vec![];
        if let Target::EdgeChain { surfaces } = &reference.target {
            let edges = |surface: &str| -> BTreeSet<usize> {
                topology
                    .faces
                    .iter()
                    .filter(|f| f.surface == surface)
                    .flat_map(|f| &f.loops)
                    .flatten()
                    .map(|u| u.edge)
                    .collect()
            };
            edge_indices = edges(&surfaces[0])
                .intersection(&edges(&surfaces[1]))
                .copied()
                .collect();
            if edge_indices.is_empty() {
                return Err(error(
                    "reference_missing",
                    name,
                    "The selected surfaces no longer share an edge",
                ));
            }
            // A physical circle can span four quarter arcs. Reject disconnected
            // intersections, branches and mixed curves instead of choosing a patch.
            let curve = &topology.edges[edge_indices[0]].curve;
            let mut adjacency: BTreeMap<usize, Vec<usize>> = BTreeMap::new();
            for &i in &edge_indices {
                let edge = &topology.edges[i];
                if &edge.curve != curve {
                    return Err(error(
                        "reference_ambiguous",
                        name,
                        "Surface intersection contains different curves",
                    ));
                }
                let [a, b] = edge.vertices;
                adjacency.entry(a).or_default().push(b);
                adjacency.entry(b).or_default().push(a);
            }
            let ends = adjacency.values().filter(|v| v.len() == 1).count();
            if ![0, 2].contains(&ends) || adjacency.values().any(|v| v.len() > 2) {
                return Err(error(
                    "reference_ambiguous",
                    name,
                    "Surface intersection branches",
                ));
            }
            let mut todo = vec![*adjacency.keys().next().unwrap()];
            let mut seen = BTreeSet::new();
            while let Some(v) = todo.pop() {
                if seen.insert(v) {
                    todo.extend(&adjacency[&v]);
                }
            }
            if seen.len() != adjacency.len() {
                return Err(error(
                    "reference_ambiguous",
                    name,
                    "Surface intersection has separate edge chains",
                ));
            }
        }
        result.insert(
            name.clone(),
            Resolved {
                feature_id: reference.feature_id.clone(),
                target: reference.target.clone(),
                face_ids,
                edge_indices,
            },
        );
    }
    Ok(result)
}
