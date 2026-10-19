//! Bounded exact affine relationships over named millimeter parameters.
use super::{error, identifier, parameter, rational, Model, Result, Q};
use num_traits::Zero;
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Relation {
    pub offset_mm: String,
    /// Dimensionless rational coefficient for each referenced mm parameter.
    pub terms: BTreeMap<String, String>,
}

pub(super) fn require_free(model: &Model, id: &str) -> Result<()> {
    if model.relations.contains_key(id) {
        return Err(error(
            "derived_parameter",
            id,
            "Edit the relationship or its inputs, or explicitly remove the relationship before setting this parameter",
        ));
    }
    Ok(())
}

fn bounded(value: Q, id: &str) -> Result<Q> {
    if value.numer().bits() > 128 || value.denom().bits() > 128 {
        return Err(error(
            "relation_overflow",
            id,
            "Relationship intermediate/result exceeds 128-bit numerator or denominator",
        ));
    }
    Ok(value)
}

fn visit(
    id: &str,
    model: &Model,
    values: &mut BTreeMap<String, Q>,
    visiting: &mut Vec<String>,
) -> Result<Q> {
    if let Some(value) = values.get(id) {
        return Ok(value.clone());
    }
    if let Some(start) = visiting.iter().position(|v| v == id) {
        let mut cycle = visiting[start..].to_vec();
        cycle.push(id.into());
        return Err(error(
            "relation_cycle",
            id,
            &format!("Dependency cycle: {}", cycle.join(" -> ")),
        ));
    }
    let stored = parameter(model, id)?;
    visiting.push(id.into());
    let value = if let Some(relation) = model.relations.get(id) {
        let mut value = rational(&relation.offset_mm, id)?;
        for (dependency, coefficient) in &relation.terms {
            let coefficient = rational(coefficient, id)?;
            let input = visit(dependency, model, values, visiting)?;
            let term = bounded(coefficient * input, id)?;
            value = bounded(value + term, id)?;
        }
        value
    } else {
        stored
    };
    visiting.pop();
    values.insert(id.into(), value.clone());
    Ok(value)
}

fn resolve(model: &Model) -> Result<BTreeMap<String, Q>> {
    // Bound recursion and work before traversing even malformed input graphs.
    if model.parameters.len() > 64 || model.relations.len() > 64 {
        return Err(error(
            "model_limit",
            "model",
            "Maximum 64 parameters and relationships",
        ));
    }
    for (id, relation) in &model.relations {
        identifier(id)?;
        parameter(model, id)?;
        rational(&relation.offset_mm, id)?;
        if relation.terms.len() > 8 {
            return Err(error(
                "relation_limit",
                id,
                "Maximum 8 terms per relationship",
            ));
        }
        for (dependency, coefficient) in &relation.terms {
            identifier(dependency)?;
            parameter(model, dependency)?;
            if rational(coefficient, id)?.is_zero() {
                return Err(error("invalid_relation", id, "Omit zero-coefficient terms"));
            }
        }
    }
    let mut values = BTreeMap::new();
    for id in model.parameters.keys() {
        visit(id, model, &mut values, &mut Vec::new())?;
    }
    Ok(values)
}

pub(super) fn refresh(model: &mut Model) -> Result<()> {
    let values = resolve(model)?;
    for id in model.relations.keys() {
        model.parameters.insert(id.clone(), values[id].to_string());
    }
    Ok(())
}

pub(super) fn validate(model: &Model) -> Result<()> {
    let values = resolve(model)?;
    for id in model.relations.keys() {
        if parameter(model, id)? != values[id] {
            return Err(error(
                "relation_mismatch",
                id,
                "Stored derived value does not match its relationship; edit through modeling operations",
            ));
        }
    }
    Ok(())
}
