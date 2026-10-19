use super::math::value;
use super::{limit, Result, MAX_CELLS, MAX_CELL_FACES};
use boundary_clip::{Boundary, Plane, Request};

pub(super) fn budget(cells: &[Boundary]) -> Result<()> {
    if cells.len() > MAX_CELLS
        || cells.iter().map(|c| c.faces.len()).sum::<usize>() > MAX_CELL_FACES
    {
        return Err(limit("Maximum 32 convex cells and 256 cell faces"));
    }
    Ok(())
}
pub(super) fn clip(cell: &Boundary, plane: Plane) -> Result<Option<Boundary>> {
    let reply = boundary_clip::clip(Request {
        schema_version: 1,
        boundary: cell.clone(),
        plane,
    })
    .map_err(|e| super::fail(&e))?;
    Ok(if reply.classification == "empty" {
        None
    } else {
        Some(reply.boundary)
    })
}
pub(super) fn intersection(left: &Boundary, right: &Boundary) -> Result<Option<Boundary>> {
    let mut current = left.clone();
    for face in &right.faces {
        match clip(
            &current,
            Plane {
                normal: face.normal.clone(),
                offset: face.offset.clone(),
            },
        )? {
            Some(next) => current = next,
            None => return Ok(None),
        }
    }
    Ok(Some(current))
}
fn subtract(subject: &Boundary, cutter: &Boundary) -> Result<Vec<Boundary>> {
    // Early disjoint/containment handling avoids unnecessary subdivisions.
    if intersection(subject, cutter)?.is_none() {
        return Ok(vec![subject.clone()]);
    }
    let mut current = subject.clone();
    let mut pieces = vec![];
    for face in &cutter.faces {
        let n = [
            value(&face.normal[0])?,
            value(&face.normal[1])?,
            value(&face.normal[2])?,
        ];
        let d = value(&face.offset)?;
        if let Some(outside) = clip(
            &current,
            Plane {
                normal: n.map(|v| (-v).to_string()),
                offset: (-&d).to_string(),
            },
        )? {
            pieces.push(outside);
            budget(&pieces)?;
        }
        match clip(
            &current,
            Plane {
                normal: face.normal.clone(),
                offset: d.to_string(),
            },
        )? {
            Some(inside) => current = inside,
            None => break,
        }
    }
    Ok(pieces)
}
pub(super) fn difference(mut cells: Vec<Boundary>, cutters: &[Boundary]) -> Result<Vec<Boundary>> {
    for cutter in cutters {
        let mut next = vec![];
        for cell in &cells {
            next.extend(subtract(cell, cutter)?);
            budget(&next)?;
        }
        cells = next;
        if cells.is_empty() {
            break;
        }
    }
    Ok(cells)
}
