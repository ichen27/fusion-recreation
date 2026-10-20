//! Full turns of simple rational radius/Z profiles; no angular approximation.
use crate::{
    error,
    holes::{AnalyticPrism, ExactVolume},
    profile::Profile,
    Result, Q,
};
use num_traits::{Signed, Zero};
use serde::Serialize;

#[derive(Clone, Debug, Serialize)]
pub struct Revolution {
    pub points: Vec<[String; 2]>,
    pub roles: Vec<String>,
    pub axis_contact: bool,
}
fn q(n: i32) -> Q {
    Q::from_integer(n.into())
}

pub(crate) fn resolve(id: &str, profile: &Profile) -> Result<AnalyticPrism> {
    let mut points = profile.points.clone();
    let mut names = profile.vertex_ids.clone();
    let invalid = || {
        error("unsupported_revolution", id, "Use a simple radius/Z polygon with nonnegative radii; axis contact requires one connected axis edge with flat end faces. Apexes, pinches and partial turns are unsupported")
    };
    if points.iter().any(|p| p[0].is_negative()) {
        return Err(invalid());
    }
    let zeros: Vec<_> = (0..points.len())
        .filter(|&i| points[i][0].is_zero())
        .collect();
    if !zeros.is_empty() {
        if zeros.len() != 2
            || !((zeros[0] + 1) % points.len() == zeros[1]
                || (zeros[1] + 1) % points.len() == zeros[0])
        {
            return Err(invalid());
        }
        for &i in &zeros {
            for j in [
                (i + points.len() - 1) % points.len(),
                (i + 1) % points.len(),
            ] {
                if !points[j][0].is_zero() && points[j][1] != points[i][1] {
                    return Err(invalid());
                }
            }
        }
    }
    if profile.twice_area.is_negative() {
        points.reverse();
        names.reverse();
    }
    let roles = (0..points.len())
        .map(|i| {
            let mut pair = [names[i].clone(), names[(i + 1) % names.len()].clone()];
            pair.sort();
            format!("profile/edge/{}/{}", pair[0], pair[1])
        })
        .collect();
    let volume = integrate(&points, 2, 0);
    if !volume.is_positive() {
        return Err(invalid());
    }
    let lo = points.iter().map(|p| &p[1]).min().unwrap();
    let hi = points.iter().map(|p| &p[1]).max().unwrap();
    Ok(AnalyticPrism {
        placement: None,
        kind: "revolved_profile",
        outer: vec![],
        outer_circle: None,
        height: (hi - lo).to_string(),
        top_radius: None,
        hole_depth: None,
        counterbore: None,
        countersink: None,
        holes: vec![],
        revolution: Some(Revolution {
            points: points
                .into_iter()
                .map(|p| p.map(|v| v.to_string()))
                .collect(),
            roles,
            axis_contact: !zeros.is_empty(),
        }),
        volume: ExactVolume {
            constant_mm3: "0".into(),
            pi_subtract_mm3: (-volume).to_string(),
        },
    })
}
fn choose(n: usize, k: usize) -> i32 {
    (0..k).fold(1, |value, i| value * (n - i) as i32 / (i + 1) as i32)
}
// Green's theorem: volume/pi = integral around boundary of r² dz.
// Higher radial/axial powers give volume moments by the same exact polynomial integral.
pub(crate) fn integrate(points: &[[Q; 2]], radial: usize, axial: usize) -> Q {
    let mut result = q(0);
    for (a, b) in points
        .iter()
        .zip(points.iter().cycle().skip(1))
        .take(points.len())
    {
        let dr = &b[0] - &a[0];
        let dz = &b[1] - &a[1];
        for k in 0..=radial {
            for l in 0..=axial {
                result += &dz
                    * q(choose(radial, k) * choose(axial, l))
                    * a[0].pow((radial - k) as i32)
                    * dr.pow(k as i32)
                    * a[1].pow((axial - l) as i32)
                    * dz.pow(l as i32)
                    / q((k + l + 1) as i32);
            }
        }
    }
    result
}
