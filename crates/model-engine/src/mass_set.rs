//! Read-only additive mass of distinct terminal occurrences, with explicit densities.
use crate::{error, measure as moments, rational, Model, Result, Q};
use num_traits::{One, Signed, Zero};
use serde::{Deserialize, Serialize};
use std::collections::BTreeSet;

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Request {
    pub model: Model,
    pub parts: Vec<Part>,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Part {
    pub feature_id: String,
    pub density_kg_per_m3: String,
}
#[derive(Serialize)]
pub struct Measurements {
    pub mass_kg: String,
    pub center_of_mass_mm: [String; 3],
    pub centroidal_inertia_kg_m2: [[String; 3]; 3],
    pub overlap_policy: &'static str,
    pub parts: Vec<moments::Measurements>,
}

// Geometry supplies trusted exact expressions. Retain symbolic products rather
// than rounding pi or expanding them into high-degree polynomials. Rational-only
// workloads stay reduced. Bound every constructed expression before allocating.
#[derive(Clone, PartialEq)]
enum Exact {
    Rational(Q),
    Symbolic(String),
}
impl Exact {
    fn zero() -> Self {
        Self::Rational(Q::zero())
    }
    fn input(s: &str) -> Result<Self> {
        if s.len() > 65_536 {
            return Err(limit());
        }
        match s.parse::<Q>() {
            Ok(q) => {
                moments::bounded(&q)?;
                Ok(Self::Rational(q))
            }
            Err(_) => Ok(Self::Symbolic(s.into())),
        }
    }
    fn text(&self) -> String {
        match self {
            Self::Rational(q) => q.to_string(),
            Self::Symbolic(s) => s.clone(),
        }
    }
    fn is_zero(&self) -> bool {
        matches!(self, Self::Rational(q) if q.is_zero())
    }
    fn is_one(&self) -> bool {
        matches!(self, Self::Rational(q) if q.is_one())
    }
    fn op(&self, rhs: &Self, op: char) -> Result<Self> {
        if let (Self::Rational(a), Self::Rational(b)) = (self, rhs) {
            if op == '/' && b.is_zero() {
                return Err(error("invalid_mass", "mass_set", "Zero total mass"));
            }
            let q = match op {
                '+' => a + b,
                '-' => a - b,
                '*' => a * b,
                '/' => a / b,
                _ => unreachable!(),
            };
            moments::bounded(&q)?;
            return Ok(Self::Rational(q));
        }
        if op == '-' && self == rhs {
            return Ok(Self::zero());
        }
        match op {
            '+' if self.is_zero() => return Ok(rhs.clone()),
            '+' | '-' if rhs.is_zero() => return Ok(self.clone()),
            '*' if self.is_zero() || rhs.is_zero() => return Ok(Self::zero()),
            '*' if self.is_one() => return Ok(rhs.clone()),
            '*' | '/' if rhs.is_one() => return Ok(self.clone()),
            _ => {}
        }
        let a = self.text();
        let b = rhs.text();
        if a.len() + b.len() + 5 > 65_536 {
            return Err(limit());
        }
        Ok(Self::Symbolic(format!("({a}){op}({b})")))
    }
}
fn limit() -> crate::Error {
    error(
        "mass_limit",
        "mass_set",
        "Exact expression exceeds 65536 bytes; measure a smaller selection",
    )
}

pub fn measure(mut request: Request) -> Result<Measurements> {
    if !(1..=16).contains(&request.parts.len()) {
        return Err(error(
            "mass_limit",
            "mass_set",
            "Select 1..16 distinct terminal solids",
        ));
    }
    // Canonical order makes results deterministic for the same selected set.
    request
        .parts
        .sort_by(|a, b| a.feature_id.cmp(&b.feature_id));
    let mut ids = BTreeSet::new();
    let mut densities = Vec::new();
    for part in &request.parts {
        crate::identifier(&part.feature_id)?;
        if !ids.insert(&part.feature_id) {
            return Err(error(
                "duplicate_id",
                &part.feature_id,
                "Select each occurrence only once",
            ));
        }
        let density = rational(&part.density_kg_per_m3, &part.feature_id)?;
        if !density.is_positive() {
            return Err(error(
                "invalid_density",
                &part.feature_id,
                "Uniform density must be positive",
            ));
        }
        densities.push(density);
    }
    let evaluated = crate::evaluate(crate::Request {
        schema_version: 1,
        model: request.model,
        operations: vec![],
        preserve: vec![],
    })?;
    let mut parts = Vec::new();
    let mut masses = Vec::new();
    let mut centers = Vec::new();
    let mut total = Exact::zero();
    let mut first: [Exact; 3] = std::array::from_fn(|_| Exact::zero());
    for (part, density) in request.parts.iter().zip(densities) {
        let measured = moments::with_density(
            moments::from_evaluation(&evaluated, &part.feature_id)?,
            Some(density),
        )?;
        let mass = Exact::input(&measured.mass_properties.as_ref().unwrap().mass_kg)?;
        let center = measured
            .centroid_mm
            .iter()
            .map(|c| Exact::input(c))
            .collect::<Result<Vec<_>>>()?;
        total = total.op(&mass, '+')?;
        for i in 0..3 {
            first[i] = first[i].op(&mass.op(&center[i], '*')?, '+')?;
        }
        masses.push(mass);
        centers.push(center);
        parts.push(measured);
    }
    // Every native volume and requested density is positive, so total cannot
    // vanish even when represented symbolically. No floating positivity test.
    let center = (0..3)
        .map(|i| {
            if centers.iter().all(|c| c[i] == centers[0][i]) {
                Ok(centers[0][i].clone())
            } else {
                first[i].op(&total, '/')
            }
        })
        .collect::<Result<Vec<_>>>()?;
    let mut tensor: [[Exact; 3]; 3] =
        std::array::from_fn(|_| std::array::from_fn(|_| Exact::zero()));
    let thousand = Exact::Rational(Q::from_integer(1000.into()));
    for (index, part) in parts.iter().enumerate() {
        let delta = (0..3)
            .map(|i| centers[index][i].op(&center[i], '-')?.op(&thousand, '/'))
            .collect::<Result<Vec<_>>>()?;
        let own = &part
            .mass_properties
            .as_ref()
            .unwrap()
            .centroidal_inertia_kg_m2;
        for i in 0..3 {
            for j in i..3 {
                let shift = if i == j {
                    let mut sum = Exact::zero();
                    for (k, d) in delta.iter().enumerate() {
                        if k != i {
                            sum = sum.op(&d.op(d, '*')?, '+')?;
                        }
                    }
                    sum
                } else {
                    Exact::zero().op(&delta[i].op(&delta[j], '*')?, '-')?
                };
                let entry = Exact::input(&own[i][j])?.op(&masses[index].op(&shift, '*')?, '+')?;
                tensor[i][j] = tensor[i][j].op(&entry, '+')?;
            }
        }
    }
    for i in 0..3 {
        for j in 0..i {
            tensor[i][j] = tensor[j][i].clone();
        }
    }
    Ok(Measurements {
        mass_kg: total.text(),
        center_of_mass_mm: std::array::from_fn(|i| center[i].text()),
        centroidal_inertia_kg_m2: tensor.map(|row| row.map(|v| v.text())),
        overlap_policy: "count_each_selected_occurrence",
        parts,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn expression_and_rational_budgets_are_enforced() {
        let long = Exact::Symbolic("pi+".repeat(20_000) + "pi");
        assert_eq!(long.op(&long, '+').err().unwrap().code, "mass_limit");
        let large = Exact::Rational(Q::from_integer(crate::BigInt::from(1) << 8191));
        assert_eq!(
            large.op(&large, '*').err().unwrap().code,
            "measurement_limit"
        );
        assert!(long.op(&long, '-').unwrap().is_zero());
        assert!(long.op(&Exact::zero(), '*').unwrap().is_zero());
    }
}
