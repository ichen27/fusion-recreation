//! Original exact planar cell Booleans with merged manifold boundary output.
//! Ports the checked-in planar research algorithm; no external modeling fallback.
mod boundary;
mod cells;
mod math;
use crate::{error, Result, Q};
use boundary_clip::Boundary;
use serde::{Deserialize, Serialize};

const MAX_CELLS: usize = 32;
const MAX_CELL_FACES: usize = 256;
const MAX_PATCHES: usize = 512;
const MAX_VERTICES: usize = 512;
const MAX_FACES: usize = 256;
const MAX_EDGES: usize = 1024;

fn fail(message: &str) -> crate::Error {
    error("invalid_polyhedron", "boolean", message)
}
fn limit(message: &str) -> crate::Error {
    error("polyhedral_limit", "boolean", message)
}

#[derive(Clone, Copy, Debug, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Operation {
    Union,
    Difference,
    Intersection,
}

#[derive(Clone, Debug)]
pub struct Solid {
    pub(crate) cells: Vec<Boundary>,
    pub(crate) boundary: Boundary,
    pub(crate) components: Vec<Vec<usize>>,
    pub(crate) volume: Q,
}

impl Solid {
    pub fn from_convex(boundary: Boundary) -> Result<Self> {
        let plane = boundary
            .faces
            .first()
            .map(|f| boundary_clip::Plane {
                normal: f.normal.clone(),
                offset: f.offset.clone(),
            })
            .ok_or_else(|| fail("A convex input must have faces"))?;
        let checked = boundary_clip::clip(boundary_clip::Request {
            schema_version: 1,
            boundary,
            plane,
        })
        .map_err(|e| fail(&e))?;
        if checked.classification == "empty" {
            return Err(fail("A convex input must have positive volume"));
        }
        Self::from_cells(vec![checked.boundary])
    }
    fn from_cells(cells: Vec<Boundary>) -> Result<Self> {
        cells::budget(&cells)?;
        if cells.is_empty() {
            return Err(error(
                "empty_solid",
                "boolean",
                "Boolean leaves no positive-volume solid",
            ));
        }
        let (boundary, components, volume) = boundary::build(&cells)?;
        Ok(Self {
            cells,
            boundary,
            components,
            volume,
        })
    }
    pub fn combine(&self, other: &Self, operation: Operation) -> Result<Self> {
        let cells = match operation {
            Operation::Difference => cells::difference(self.cells.clone(), &other.cells)?,
            Operation::Union => {
                let mut cells = self.cells.clone();
                cells.extend(cells::difference(other.cells.clone(), &self.cells)?);
                cells
            }
            Operation::Intersection => {
                let mut cells = vec![];
                for left in &self.cells {
                    for right in &other.cells {
                        if let Some(cell) = cells::intersection(left, right)? {
                            cells.push(cell);
                            cells::budget(&cells)?;
                        }
                    }
                }
                cells
            }
        };
        Self::from_cells(cells)
    }
}

#[cfg(test)]
mod tests;
