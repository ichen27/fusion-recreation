//! Compile bounded simultaneous linear equalities into persistent affine rules.
//! Exact elimination is symbolic in the remaining parameters, so constraints
//! continue to hold after driver edits rather than only at today's values.
use crate::{error, identifier, parameter, rational, Model, Relation, Result, Q};
use num_traits::Zero;
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet};

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct LinearEquation {
    pub id: String,
    /// sum(terms[parameter] * parameter) = offset_mm.
    pub terms: BTreeMap<String, String>,
    pub offset_mm: String,
}
fn bounded(value: Q) -> Result<Q> {
    if value.numer().bits() > 128 || value.denom().bits() > 128 {
        return Err(error(
            "linear_overflow",
            "linear",
            "Elimination intermediate/result exceeds 128-bit numerator or denominator",
        ));
    }
    Ok(value)
}

pub(crate) fn compile(
    model: &Model,
    targets: &[String],
    equations: &[LinearEquation],
) -> Result<BTreeMap<String, Relation>> {
    if model.parameters.len() > 64
        || !(1..=16).contains(&targets.len())
        || !(1..=32).contains(&equations.len())
    {
        return Err(error(
            "linear_limit",
            "linear",
            "Use 1..16 target parameters, 1..32 equations and at most 64 model parameters",
        ));
    }
    let mut target_set = BTreeSet::new();
    for id in targets {
        identifier(id)?;
        parameter(model, id)?;
        if !target_set.insert(id.clone()) {
            return Err(error("duplicate_id", id, "Target parameter repeats"));
        }
    }
    let targets: Vec<_> = target_set.iter().cloned().collect();
    let mut names = BTreeSet::new();
    let mut drivers = BTreeSet::new();
    for equation in equations {
        identifier(&equation.id)?;
        if !names.insert(equation.id.clone()) {
            return Err(error("duplicate_id", &equation.id, "Equation ID repeats"));
        }
        rational(&equation.offset_mm, &equation.id)?;
        if equation.terms.len() > 8 {
            return Err(error(
                "linear_limit",
                &equation.id,
                "Maximum 8 nonzero terms per equation",
            ));
        }
        for (id, coefficient) in &equation.terms {
            identifier(id)?;
            parameter(model, id)?;
            if rational(coefficient, &equation.id)?.is_zero() {
                return Err(error(
                    "invalid_linear_equation",
                    &equation.id,
                    "Omit zero-coefficient terms",
                ));
            }
            if !target_set.contains(id) {
                drivers.insert(id.clone());
            }
        }
    }
    let drivers: Vec<_> = drivers.into_iter().collect();
    let columns: Vec<_> = targets.iter().chain(&drivers).collect();
    let n = targets.len();
    let width = columns.len() + 1;
    let mut rows: Vec<Vec<Q>> = equations
        .iter()
        .map(|equation| {
            let mut row: Vec<Q> = columns
                .iter()
                .enumerate()
                .map(|(i, id)| {
                    let v = equation
                        .terms
                        .get(*id)
                        .map(|c| rational(c, &equation.id))
                        .transpose()?
                        .unwrap_or_else(Q::zero);
                    Ok(if i < n { v } else { -v })
                })
                .collect::<Result<_>>()?;
            row.push(rational(&equation.offset_mm, &equation.id)?);
            Ok(row)
        })
        .collect::<Result<_>>()?;
    let mut sources: Vec<BTreeSet<String>> = equations
        .iter()
        .map(|e| BTreeSet::from([e.id.clone()]))
        .collect();
    let mut pivots = Vec::new();
    for column in 0..n {
        let rank = pivots.len();
        let Some(found) = (rank..rows.len()).find(|&i| !rows[i][column].is_zero()) else {
            continue;
        };
        rows.swap(rank, found);
        sources.swap(rank, found);
        let divisor = rows[rank][column].clone();
        for value in &mut rows[rank] {
            *value = bounded(&*value / &divisor)?;
        }
        let pivot = rows[rank].clone();
        let provenance = sources[rank].clone();
        for i in 0..rows.len() {
            if i == rank || rows[i][column].is_zero() {
                continue;
            }
            let factor = rows[i][column].clone();
            for (value, pivot_value) in rows[i].iter_mut().zip(&pivot) {
                let product = bounded(&factor * pivot_value)?;
                *value = bounded(&*value - product)?;
            }
            sources[i].extend(provenance.iter().cloned());
        }
        pivots.push(column);
    }
    for (row, source) in rows.iter().zip(&sources) {
        if row[..n].iter().all(Zero::is_zero) {
            let ids = source.iter().cloned().collect::<Vec<_>>().join(", ");
            if row[n..width - 1].iter().any(|v| !v.is_zero()) {
                return Err(error("linear_driver_constraint", "linear", &format!("Equations involving {ids} also constrain non-target drivers; include the dependent driver among targets or revise the equations")));
            }
            if !row[width - 1].is_zero() {
                return Err(error(
                    "linear_inconsistent",
                    "linear",
                    &format!("Equations involving {ids} contradict each other"),
                ));
            }
        }
    }
    if pivots.len() != n {
        let free: Vec<_> = targets
            .iter()
            .enumerate()
            .filter(|(i, _)| !pivots.contains(i))
            .map(|(_, id)| id.as_str())
            .collect();
        return Err(error("linear_underdetermined", "linear", &format!("Rank {} for {n} targets; unbound targets: {}. Add independent equations or leave these as drivers",pivots.len(),free.join(", "))));
    }
    let mut solved = BTreeMap::new();
    for (i, id) in targets.into_iter().enumerate() {
        let terms: BTreeMap<_, _> = drivers
            .iter()
            .enumerate()
            .filter(|(j, _)| !rows[i][n + j].is_zero())
            .map(|(j, id)| (id.clone(), rows[i][n + j].to_string()))
            .collect();
        if terms.len() > 8 {
            return Err(error(
                "linear_limit",
                &id,
                "Solved relationship exceeds 8 input terms",
            ));
        }
        solved.insert(
            id,
            Relation {
                offset_mm: rows[i][width - 1].to_string(),
                terms,
            },
        );
    }
    Ok(solved)
}
