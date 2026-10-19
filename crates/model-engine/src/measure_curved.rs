//! Exact rational functions of pi for analytic prism volume moments.
use crate::{
    error,
    measure::{bounded, value, Measurements},
    AnalyticPrism, Result, Q,
};
use num_traits::Zero;
type Linear = [Q; 2];
type Polynomial = [Q; 3];
fn q(n: i32) -> Q {
    Q::from_integer(n.into())
}
fn product(a: &Linear, b: &Linear) -> Polynomial {
    [&a[0] * &b[0], &a[0] * &b[1] + &a[1] * &b[0], &a[1] * &b[1]]
}
fn subtract(a: &Polynomial, b: &Polynomial) -> Polynomial {
    std::array::from_fn(|i| &a[i] - &b[i])
}
fn polynomial(p: &Polynomial) -> String {
    let terms: Vec<_> = p
        .iter()
        .enumerate()
        .filter(|(_, c)| !c.is_zero())
        .map(|(i, c)| match i {
            0 => c.to_string(),
            1 => format!("({c})*pi"),
            _ => format!("({c})*pi*pi"),
        })
        .collect();
    if terms.is_empty() {
        "0".into()
    } else {
        terms.join(" + ")
    }
}
fn quotient(mut numerator: Polynomial, denominator: &Linear) -> Result<String> {
    for c in numerator.iter().chain(denominator) {
        bounded(c)?;
    }
    if denominator.iter().all(Zero::is_zero) {
        return Err(error(
            "invalid_geometry",
            "measurement",
            "Zero symbolic volume",
        ));
    }
    if denominator[1].is_zero() {
        let divided = numerator.map(|c| c / &denominator[0]);
        for c in &divided {
            bounded(c)?;
        }
        return Ok(polynomial(&divided));
    }
    let original = numerator.clone();
    let mut divided: Polynomial = std::array::from_fn(|_| q(0));
    for i in (1..=2).rev() {
        let coefficient = &numerator[i] / &denominator[1];
        divided[i - 1] = coefficient.clone();
        numerator[i] -= &coefficient * &denominator[1];
        numerator[i - 1] -= &coefficient * &denominator[0];
    }
    for c in divided.iter().chain(&numerator) {
        bounded(c)?;
    }
    if numerator.iter().all(Zero::is_zero) {
        Ok(polynomial(&divided))
    } else {
        Ok(format!(
            "({})/({})",
            polynomial(&original),
            polynomial(&[denominator[0].clone(), denominator[1].clone(), q(0)])
        ))
    }
}

// Integrate z^moment * (r0 + (r1-r0) z/h)^power over [0,h].
fn radial_integral(r0: &Q, r1: &Q, h: &Q, power: usize, moment: usize) -> Q {
    let delta = r1 - r0;
    let mut choose = 1;
    let mut sum = q(0);
    for k in 0..=power {
        sum += q(choose) * r0.pow((power - k) as i32) * delta.pow(k as i32)
            / q((k + moment + 1) as i32);
        if k < power {
            choose = choose * (power - k) as i32 / (k + 1) as i32;
        }
    }
    h.pow((moment + 1) as i32) * sum
}

pub(crate) fn measure(id: &str, shape: &AnalyticPrism, volume_text: &str) -> Result<Measurements> {
    let height = value(&shape.height)?;
    let mut volume: Linear = [q(0), q(0)];
    let mut first: [Linear; 3] = std::array::from_fn(|_| [q(0), q(0)]);
    let mut second: [[Linear; 3]; 3] =
        std::array::from_fn(|_| std::array::from_fn(|_| [q(0), q(0)]));
    let mut bounds: [[Q; 3]; 2] = std::array::from_fn(|_| std::array::from_fn(|_| q(0)));
    bounds[1][2] = height.clone();
    if let Some(circle) = &shape.outer_circle {
        let x = value(&circle.center[0])?;
        let y = value(&circle.center[1])?;
        let bottom_r = value(&circle.radius)?;
        let r = shape
            .top_radius
            .as_ref()
            .map(|s| value(s))
            .transpose()?
            .unwrap_or(bottom_r.clone())
            .max(bottom_r);
        bounds[0][0] = &x - &r;
        bounds[1][0] = &x + &r;
        bounds[0][1] = &y - &r;
        bounds[1][1] = &y + &r;
    } else {
        let points = shape
            .outer
            .iter()
            .map(|p| Ok([value(&p[0])?, value(&p[1])?]))
            .collect::<Result<Vec<_>>>()?;
        for axis in 0..2 {
            bounds[0][axis] = points.iter().map(|p| p[axis].clone()).min().unwrap();
            bounds[1][axis] = points.iter().map(|p| p[axis].clone()).max().unwrap();
        }
        let mut area = q(0);
        let mut planar_first = [q(0), q(0)];
        let mut planar_second = [[q(0), q(0)], [q(0), q(0)]];
        for i in 0..points.len() {
            let (a, b) = (&points[i], &points[(i + 1) % points.len()]);
            let cross = &a[0] * &b[1] - &b[0] * &a[1];
            area += &cross / q(2);
            for axis in 0..2 {
                planar_first[axis] += (&a[axis] + &b[axis]) * &cross / q(6);
                planar_second[axis][axis] +=
                    (&a[axis] * &a[axis] + &a[axis] * &b[axis] + &b[axis] * &b[axis]) * &cross
                        / q(12);
            }
            planar_second[0][1] +=
                (q(2) * &a[0] * &a[1] + &a[0] * &b[1] + &b[0] * &a[1] + q(2) * &b[0] * &b[1])
                    * &cross
                    / q(24);
        }
        planar_second[1][0] = planar_second[0][1].clone();
        volume[0] = &area * &height;
        first[2][0] = &area * &height * &height / q(2);
        second[2][2][0] = &area * &height * &height * &height / q(3);
        for i in 0..2 {
            first[i][0] = &planar_first[i] * &height;
            second[i][2][0] = &planar_first[i] * &height * &height / q(2);
            second[2][i][0] = second[i][2][0].clone();
            for j in 0..2 {
                second[i][j][0] = &planar_second[i][j] * &height;
            }
        }
    }
    let depth = shape
        .hole_depth
        .as_ref()
        .map(|s| value(s))
        .transpose()?
        .unwrap_or(height.clone());
    let mut disks = Vec::new();
    if let Some(c) = &shape.outer_circle {
        if let Some(top) = &shape.top_radius {
            let x = value(&c.center[0])?;
            let y = value(&c.center[1])?;
            let r0 = value(&c.radius)?;
            let r1 = value(top)?;
            let v = radial_integral(&r0, &r1, &height, 2, 0);
            let z1 = radial_integral(&r0, &r1, &height, 2, 1);
            let z2 = radial_integral(&r0, &r1, &height, 2, 2);
            let radial_second = radial_integral(&r0, &r1, &height, 4, 0) / q(4);
            volume[1] = v.clone();
            first[0][1] = &x * &v;
            first[1][1] = &y * &v;
            first[2][1] = z1.clone();
            second[0][0][1] = &x * &x * &v + &radial_second;
            second[1][1][1] = &y * &y * &v + radial_second;
            second[2][2][1] = z2;
            second[0][1][1] = &x * &y * &v;
            second[1][0][1] = second[0][1][1].clone();
            second[0][2][1] = &x * &z1;
            second[2][0][1] = second[0][2][1].clone();
            second[1][2][1] = &y * &z1;
            second[2][1][1] = second[1][2][1].clone();
        } else {
            disks.push((
                value(&c.center[0])?,
                value(&c.center[1])?,
                value(&c.radius)?,
                q(0),
                height.clone(),
                q(1),
            ));
        }
    }
    for c in &shape.holes {
        disks.push((
            value(&c.center[0])?,
            value(&c.center[1])?,
            value(&c.radius)?,
            &height
                - c.depth
                    .as_ref()
                    .map(|s| value(s))
                    .transpose()?
                    .unwrap_or(depth.clone()),
            height.clone(),
            q(-1),
        ));
    }
    if let Some(bore) = &shape.counterbore {
        let radius = value(&bore.radius)?;
        let floor = &height - value(&bore.depth)?;
        for hole in &shape.holes {
            let x = value(&hole.center[0])?;
            let y = value(&hole.center[1])?;
            // Remove only the upper annulus; the small through cylinder is already subtracted.
            disks.push((
                x.clone(),
                y.clone(),
                radius.clone(),
                floor.clone(),
                height.clone(),
                q(-1),
            ));
            disks.push((
                x,
                y,
                value(&hole.radius)?,
                floor.clone(),
                height.clone(),
                q(1),
            ));
        }
    }
    if let Some(sink) = &shape.countersink {
        let top = value(&sink.radius)?;
        let d = value(&sink.depth)?;
        let floor = &height - &d;
        for hole in &shape.holes {
            let x = value(&hole.center[0])?;
            let y = value(&hole.center[1])?;
            let r = value(&hole.radius)?;
            let v = radial_integral(&r, &top, &d, 2, 0);
            let t = radial_integral(&r, &top, &d, 2, 1);
            let z = &floor * &v + &t;
            let zz =
                &floor * &floor * &v + q(2) * &floor * &t + radial_integral(&r, &top, &d, 2, 2);
            let radial_second = radial_integral(&r, &top, &d, 4, 0) / q(4);
            // Through cylinders are already removed. Restore their upper slice,
            // then subtract the full tapered recess with world-coordinate moments.
            disks.push((x.clone(), y.clone(), r, floor.clone(), height.clone(), q(1)));
            volume[1] -= &v;
            first[0][1] -= &x * &v;
            first[1][1] -= &y * &v;
            first[2][1] -= &z;
            second[0][0][1] -= &x * &x * &v + &radial_second;
            second[1][1][1] -= &y * &y * &v + radial_second;
            second[2][2][1] -= zz;
            for (i, j, term) in [(0, 1, &x * &y * &v), (0, 2, &x * &z), (1, 2, &y * &z)] {
                second[i][j][1] -= &term;
                second[j][i][1] -= term;
            }
        }
    }
    for (x, y, r, z0, z1, sign) in disks {
        let v = sign * &r * &r * (&z1 - &z0);
        let center = [x, y, (&z0 + &z1) / q(2)];
        volume[1] += &v;
        for i in 0..3 {
            first[i][1] += &v * &center[i];
            for j in 0..3 {
                let term = if i == j {
                    if i == 2 {
                        (&z0 * &z0 + &z0 * &z1 + &z1 * &z1) / q(3)
                    } else {
                        &center[i] * &center[i] + &r * &r / q(4)
                    }
                } else {
                    &center[i] * &center[j]
                };
                second[i][j][1] += &v * term;
            }
        }
    }
    if volume
        != [
            value(&shape.volume.constant_mm3)?,
            -value(&shape.volume.pi_subtract_mm3)?,
        ]
    {
        return Err(error(
            "invalid_geometry",
            id,
            "Analytic integrated volume mismatch",
        ));
    }
    for c in volume
        .iter()
        .chain(first.iter().flatten())
        .chain(second.iter().flatten().flatten())
    {
        bounded(c)?;
    }
    let central: [[Polynomial; 3]; 3] = std::array::from_fn(|i| {
        std::array::from_fn(|j| {
            subtract(
                &product(&second[i][j], &volume),
                &product(&first[i], &first[j]),
            )
        })
    });
    let trace: Polynomial = std::array::from_fn(|k| (0..3).map(|i| &central[i][i][k]).sum());
    let mut inertia: [[Polynomial; 3]; 3] = std::array::from_fn(|i| {
        std::array::from_fn(|j| {
            if i == j {
                subtract(&trace, &central[i][j])
            } else {
                central[i][j].clone().map(|c| -c)
            }
        })
    });
    if let Some(frame) = &shape.placement {
        let axes = frame.axes;
        first = std::array::from_fn(|i| {
            std::array::from_fn(|k| (0..3).map(|j| q(axes[i][j]) * &first[j][k]).sum())
        });
        for (i, moment) in first.iter_mut().enumerate() {
            let origin = value(&frame.origin[i])?;
            for (coefficient, v) in moment.iter_mut().zip(&volume) {
                *coefficient += &origin * v;
            }
        }
        inertia = std::array::from_fn(|i| {
            std::array::from_fn(|j| {
                std::array::from_fn(|k| {
                    (0..3)
                        .flat_map(|a| (0..3).map(move |b| (a, b)))
                        .map(|(a, b)| q(axes[i][a] * axes[j][b]) * &inertia[a][b][k])
                        .sum()
                })
            })
        });
        let mut placed = bounds.clone();
        for (i, row) in axes.iter().enumerate() {
            let origin = value(&frame.origin[i])?;
            let axis = (0..3).find(|&j| row[j] != 0).unwrap();
            let sign = row[axis];
            for side in 0..2 {
                placed[side][i] =
                    &origin + q(sign) * &bounds[if sign > 0 { side } else { 1 - side }][axis];
            }
        }
        bounds = placed;
    }
    let centroid = first
        .into_iter()
        .map(|p| quotient([p[0].clone(), p[1].clone(), q(0)], &volume))
        .collect::<Result<Vec<_>>>()?;
    let tensor = inertia
        .into_iter()
        .map(|row| {
            row.into_iter()
                .map(|p| quotient(p, &volume))
                .collect::<Result<Vec<_>>>()
        })
        .collect::<Result<Vec<_>>>()?;
    Ok(Measurements {
        feature_id: id.into(),
        volume_mm3: volume_text.into(),
        bounds_mm: bounds.map(|p| p.map(|c| c.to_string())),
        centroid_mm: std::array::from_fn(|i| centroid[i].clone()),
        centroidal_volume_inertia_mm5: std::array::from_fn(|i| {
            std::array::from_fn(|j| tensor[i][j].clone())
        }),
    })
}
