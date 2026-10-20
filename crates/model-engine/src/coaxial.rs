//! Exact radial-section operations for coaxial analytic solids.
use crate::{
    error, holes::AnalyticPrism, placement::Placement, profile, revolution, Body, Result, Q,
};
use num_traits::{Signed, Zero};
type Point = [Q; 2];
struct Section {
    points: Vec<Point>,
    axis: usize,
    center: [Q; 3],
}
fn q(n: i32) -> Q {
    Q::from_integer(n.into())
}
fn fail(id: &str, message: &str) -> crate::Error {
    error("unsupported_coaxial", id, message)
}
fn value(s: &str) -> Result<Q> {
    crate::topology::value(s)
}
fn cross(a: &Point, b: &Point, p: &Point) -> Q {
    (&b[0] - &a[0]) * (&p[1] - &a[1]) - (&b[1] - &a[1]) * (&p[0] - &a[0])
}
fn normalize(points: &mut [Point]) {
    let area: Q = points
        .iter()
        .zip(points.iter().cycle().skip(1))
        .take(points.len())
        .map(|(a, b)| &a[0] * &b[1] - &b[0] * &a[1])
        .sum();
    if area.is_negative() {
        points.reverse();
    }
}
fn section(body: &Body, convex_only: bool) -> Result<Section> {
    let id = &body.feature_id;
    let shape = body.analytic.as_ref().ok_or_else(|| {
        fail(
            id,
            "Choose cylinders, frusta or convex radial-profile revolutions",
        )
    })?;
    if !shape.holes.is_empty() {
        return Err(fail(id, "Perforated stock is not a coaxial radial section"));
    }
    let (mut points, center) = if let Some(profile) = &shape.revolution {
        (
            profile
                .points
                .iter()
                .map(|p| Ok([value(&p[0])?, value(&p[1])?]))
                .collect::<Result<Vec<_>>>()?,
            [q(0), q(0), q(0)],
        )
    } else if let Some(circle) = &shape.outer_circle {
        let r = value(&circle.radius)?;
        let top = shape
            .top_radius
            .as_ref()
            .map(|v| value(v))
            .transpose()?
            .unwrap_or(r.clone());
        let h = value(&shape.height)?;
        (
            vec![[q(0), q(0)], [r, q(0)], [top, h.clone()], [q(0), h]],
            [value(&circle.center[0])?, value(&circle.center[1])?, q(0)],
        )
    } else {
        return Err(fail(
            id,
            "Choose cylinders, frusta or convex radial-profile revolutions",
        ));
    };
    let identity = Placement {
        axes: [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
        origin: ["0".into(), "0".into(), "0".into()],
    };
    let frame = shape.placement.as_ref().unwrap_or(&identity);
    let origin = [
        value(&frame.origin[0])?,
        value(&frame.origin[1])?,
        value(&frame.origin[2])?,
    ];
    let mut world: [Q; 3] = std::array::from_fn(|i| {
        &origin[i] + (0..3).map(|j| q(frame.axes[i][j]) * &center[j]).sum::<Q>()
    });
    let axis = (0..3)
        .find(|&i| frame.axes[i][2] != 0)
        .ok_or_else(|| fail(id, "Invalid analytic axis"))?;
    for p in &mut points {
        p[1] = &world[axis] + q(frame.axes[axis][2]) * &p[1];
    }
    world[axis] = q(0);
    normalize(&mut points);
    // Convexity is about the radius/axial section, not the three-dimensional solid:
    // a rectangular ring section is valid despite its nonconvex solid material.
    let n = points.len();
    if convex_only
        && !(0..n).all(|i| {
            (0..n).all(|j| {
                j == i
                    || j == (i + 1) % n
                    || cross(&points[i], &points[(i + 1) % n], &points[j]).is_positive()
            })
        })
    {
        return Err(fail(id,"Coaxial intersection currently requires convex radial sections; stepped/undercut nonconvex sections are unsupported"));
    }
    Ok(Section {
        points,
        axis,
        center: world,
    })
}
fn clean(points: &mut Vec<Point>) {
    points.dedup();
    if points.len() > 1 && points.first() == points.last() {
        points.pop();
    }
    loop {
        if points.len() < 3 {
            break;
        }
        let n = points.len();
        if let Some(i) = (0..n)
            .find(|&i| cross(&points[(i + n - 1) % n], &points[i], &points[(i + 1) % n]).is_zero())
        {
            points.remove(i);
        } else {
            break;
        }
    }
}
pub(crate) fn intersect(id: &str, left: &Body, right: &Body) -> Result<AnalyticPrism> {
    let a = section(left, true)?;
    let b = section(right, true)?;
    if a.axis != b.axis || a.center != b.center {
        return Err(fail(id,"The solids must share exactly the same coordinate axis line; offset or crossing axes are unsupported"));
    }
    let mut points = a.points;
    for i in 0..b.points.len() {
        if points.is_empty() {
            break;
        }
        let (p, r) = (&b.points[i], &b.points[(i + 1) % b.points.len()]);
        let input = std::mem::take(&mut points);
        let mut previous = input.last().unwrap();
        let mut before = cross(p, r, previous);
        for current in &input {
            let after = cross(p, r, current);
            if before.is_negative() != after.is_negative() {
                let t = &before / (&before - &after);
                points.push(std::array::from_fn(|j| {
                    &previous[j] + &t * (&current[j] - &previous[j])
                }));
            }
            if !after.is_negative() {
                points.push(current.clone());
            }
            previous = current;
            before = after;
        }
        clean(&mut points);
    }
    finish(id, points, a.axis, a.center)
}
fn finish(id: &str, mut points: Vec<Point>, axis: usize, center: [Q; 3]) -> Result<AnalyticPrism> {
    clean(&mut points);
    normalize(&mut points);
    if points.len() < 3 {
        return Err(error(
            "empty_solid",
            id,
            "Coaxial inputs have no common positive volume",
        ));
    }
    if points.len() > 32 {
        return Err(error(
            "coaxial_limit",
            id,
            "Result radial section exceeds 32 corners",
        ));
    }
    let profile = profile::computed_polygon(id, points)?;
    let mut result = revolution::resolve(id, &profile)?;
    if let Some(section) = &mut result.revolution {
        section.roles = (0..section.points.len())
            .map(|i| format!("section/edge/{i}"))
            .collect();
    }
    let axes = match axis {
        0 => [[0, 0, 1], [0, 1, 0], [-1, 0, 0]],
        1 => [[1, 0, 0], [0, 0, 1], [0, -1, 0]],
        _ => [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
    };
    result.placement = Some(Placement {
        axes,
        origin: center.map(|v| v.to_string()),
    });
    Ok(result)
}

/// Combine exact radial sections directly, without temporary 3D construction cells.
pub(crate) fn boolean(
    id: &str,
    left: &Body,
    right: &Body,
    operation: crate::polyhedral::Operation,
) -> Result<AnalyticPrism> {
    let a = section(left, false)?;
    let b = section(right, false)?;
    if a.axis != b.axis || a.center != b.center {
        return Err(fail(
            id,
            "The solids must share exactly the same coordinate axis line",
        ));
    }
    let points = crate::section_boolean::combine(id, &a.points, &b.points, operation)?;
    finish(id, points, a.axis, a.center).map_err(|e| {
        if e.code == "unsupported_revolution" {
            error(
                "unsupported_coaxial_result",
                id,
                "The result needs one connected flat-ended axis edge when touching the axis",
            )
        } else {
            e
        }
    })
}
