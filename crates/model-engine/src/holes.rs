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
pub struct CircularBoundary {
    pub center: [String; 2],
    pub radius: String,
}
#[derive(Debug, Serialize)]
pub struct ExactVolume {
    pub constant_mm3: String,
    pub pi_subtract_mm3: String,
}
/// This is an analytic constructive representation, not the planar B-rep schema.
/// Exactly one constructed outer boundary: CCW polygon or circle. Circular inner
/// loops; caps at 0 and height; inward cylinder walls. Never deserialized from input.
#[derive(Debug, Serialize)]
pub struct AnalyticPrism {
    pub kind: &'static str,
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub outer: Vec<[String; 2]>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub outer_circle: Option<CircularBoundary>,
    pub height: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub hole_depth: Option<String>,
    pub holes: Vec<Circle>,
    pub volume: ExactVolume,
}
pub(super) fn resolve(
    m: &Model,
    id: &str,
    profile: &Profile,
    height: &Q,
    holes: &[Hole],
) -> Result<AnalyticPrism> {
    let (circles,sum_r2)=disks(m,id,holes,
        |x,y,r| super::profile::contains_disk(&profile.points,x,y,r),
        "Hole must lie strictly inside the profile with positive clearance from every boundary segment; tangency and breakout are unsupported")?;
    let mut shape = prism(profile, height);
    shape.kind = "perforated_prism";
    shape.holes = circles;
    shape.volume.pi_subtract_mm3 = (sum_r2 * height).to_string();
    Ok(shape)
}
fn disks(
    m: &Model,
    id: &str,
    holes: &[Hole],
    contained: impl Fn(&Q, &Q, &Q) -> bool,
    message: &str,
) -> Result<(Vec<Circle>, Q)> {
    if !(1..=16).contains(&holes.len()) {
        return Err(error("hole_limit", id, "Expected 1..16 through holes"));
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
        if !contained(&x, &y, &r) {
            return Err(error("hole_clearance", &hole.id, message));
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
    Ok((circles, sum_r2))
}

pub(super) fn prism(profile: &Profile, height: &Q) -> AnalyticPrism {
    let mut points = profile.points.clone();
    if profile.twice_area.is_negative() {
        points.reverse();
    }
    AnalyticPrism {
        kind: "polygon_prism",
        outer: points
            .into_iter()
            .map(|p| p.map(|q| q.to_string()))
            .collect(),
        outer_circle: None,
        height: height.to_string(),
        hole_depth: None,
        holes: vec![],
        volume: ExactVolume {
            constant_mm3: (profile.twice_area.abs() * height / Q::from_integer(2.into()))
                .to_string(),
            pi_subtract_mm3: "0".into(),
        },
    }
}

pub(super) fn round(
    m: &Model,
    x: &str,
    y: &str,
    radius: &str,
    height: &str,
) -> Result<AnalyticPrism> {
    let (cx, cy, r, h) = (
        parameter(m, x)?,
        parameter(m, y)?,
        positive(m, radius)?,
        positive(m, height)?,
    );
    for (id, v) in [(x, &cx), (y, &cy)] {
        if v.abs() > Q::from_integer(1_000_000.into()) {
            return Err(error(
                "coordinate_range",
                id,
                "Cylinder center coordinates must be within +/-1000000 mm",
            ));
        }
    }
    Ok(AnalyticPrism {
        kind: "round_prism",
        outer: vec![],
        outer_circle: Some(CircularBoundary {
            center: [cx.to_string(), cy.to_string()],
            radius: r.to_string(),
        }),
        height: h.to_string(),
        hole_depth: None,
        holes: vec![],
        volume: ExactVolume {
            constant_mm3: "0".into(),
            pi_subtract_mm3: (-&r * &r * &h).to_string(),
        },
    })
}
pub(super) fn resolve_round(
    m: &Model,
    id: &str,
    mut shape: AnalyticPrism,
    holes: &[Hole],
) -> Result<AnalyticPrism> {
    let outer = shape
        .outer_circle
        .as_ref()
        .ok_or_else(|| error("unsupported_reference", id, "Expected circular stock"))?;
    let (cx, cy, r, h) = (
        super::rational(&outer.center[0], id)?,
        super::rational(&outer.center[1], id)?,
        super::rational(&outer.radius, id)?,
        super::rational(&shape.height, id)?,
    );
    let (circles,sum_r2)=disks(m,id,holes,|x,y,hr| {
        let (dx,dy,gap)=(x-&cx,y-&cy,&r-hr);
        gap.is_positive() && &dx*&dx+&dy*&dy < &gap*&gap
    },"Hole must have positive clearance inside the outer circle; tangency and breakout are unsupported")?;
    shape.holes = circles;
    shape.volume.pi_subtract_mm3 = ((sum_r2 - &r * &r) * h).to_string();
    Ok(shape)
}

/// Apply a flat-bottom depth measured down from the top stock face.
pub(super) fn blind(
    m: &Model,
    id: &str,
    depth: &str,
    mut shape: AnalyticPrism,
) -> Result<AnalyticPrism> {
    let d = positive(m, depth)?;
    let h = super::rational(&shape.height, id)?;
    if d >= h {
        return Err(error("hole_depth", id, "Blind hole depth must be strictly below stock height; use through_holes for a full-depth cut"));
    }
    let mut sum_r2 = Q::zero();
    for circle in &shape.holes {
        let r = super::rational(&circle.radius, id)?;
        sum_r2 += &r * &r;
    }
    // Recompute from bounded input dimensions. Computed volume coefficients can
    // legitimately exceed the input parser's 128-bit component limit.
    let outer_r2 = match &shape.outer_circle {
        Some(outer) => {
            let r = super::rational(&outer.radius, id)?;
            &r * &r
        }
        None => Q::zero(),
    };
    shape.volume.pi_subtract_mm3 = (sum_r2 * &d - outer_r2 * h).to_string();
    shape.hole_depth = Some(d.to_string());
    Ok(shape)
}
