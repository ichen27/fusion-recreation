//! Bounded analytic prism family: exact rational disk containment and separation.
use super::{error, identifier, parameter, positive, profile::Profile, Model, Result, Q};
use num_traits::{Signed, Zero};
use serde::{Deserialize, Serialize};
use std::collections::BTreeSet;

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Hole {
    pub id: String,
    pub x: String,
    pub y: String,
    pub radius: String,
}
#[derive(Debug, Serialize)]
pub struct Circle {
    pub id: String,
    pub center: [String; 2],
    pub radius: String,
}
#[derive(Debug, Serialize)]
pub struct ExactVolume {
    pub constant_mm3: String,
    pub pi_subtract_mm3: String,
}
/// This is an analytic constructive representation, not the planar B-rep schema.
/// CCW outer loop; circular inner loops; caps at 0 and height; inward cylinder walls.
#[derive(Debug, Serialize)]
pub struct PerforatedPrism {
    pub kind: &'static str,
    pub outer: Vec<[String; 2]>,
    pub height: String,
    pub holes: Vec<Circle>,
    pub volume: ExactVolume,
}
pub(super) fn resolve(
    m: &Model,
    id: &str,
    profile: &Profile,
    height: &Q,
    holes: &[Hole],
) -> Result<PerforatedPrism> {
    if !(1..=16).contains(&holes.len()) {
        return Err(error("hole_limit", id, "Expected 1..16 through holes"));
    }
    let mut points = profile.points.clone();
    if profile.twice_area.is_negative() {
        points.reverse();
    }
    let mut ids = BTreeSet::new();
    let mut disks: Vec<(Q, Q, Q)> = Vec::new();
    let mut circles = Vec::new();
    let mut sum_r2 = Q::zero();
    for hole in holes {
        identifier(&hole.id)?;
        if !ids.insert(&hole.id) {
            return Err(error(
                "duplicate_id",
                &hole.id,
                "Hole ID repeats within group",
            ));
        }
        let (x, y, r) = (
            parameter(m, &hole.x)?,
            parameter(m, &hole.y)?,
            positive(m, &hole.radius)?,
        );
        if !super::profile::contains_disk(&points, &x, &y, &r) {
            return Err(error("hole_clearance", &hole.id, "Hole must lie strictly inside the profile with positive clearance from every boundary segment; tangency and breakout are unsupported"));
        }
        for (cx, cy, cr) in &disks {
            let (dx, dy, rr) = (&x - cx, &y - cy, &r + cr);
            if &dx * &dx + &dy * &dy <= &rr * &rr {
                return Err(error(
                    "hole_overlap",
                    &hole.id,
                    "Holes must be strictly separate; tangency and overlap are unsupported",
                ));
            }
        }
        sum_r2 += &r * &r;
        circles.push(Circle {
            id: hole.id.clone(),
            center: [x.to_string(), y.to_string()],
            radius: r.to_string(),
        });
        disks.push((x, y, r));
    }
    let mut shape = prism(profile, height);
    shape.kind = "perforated_prism";
    shape.holes = circles;
    shape.volume.pi_subtract_mm3 = (sum_r2 * height).to_string();
    Ok(shape)
}
pub(super) fn prism(profile: &Profile, height: &Q) -> PerforatedPrism {
    let mut points = profile.points.clone();
    if profile.twice_area.is_negative() {
        points.reverse();
    }
    PerforatedPrism {
        kind: "polygon_prism",
        outer: points
            .into_iter()
            .map(|p| p.map(|q| q.to_string()))
            .collect(),
        height: height.to_string(),
        holes: vec![],
        volume: ExactVolume {
            constant_mm3: (profile.twice_area.abs() * height / Q::from_integer(2.into()))
                .to_string(),
            pi_subtract_mm3: "0".into(),
        },
    }
}
