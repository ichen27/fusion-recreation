//! Request-local reuse of a fully validated, unchanged feature prefix.
//! Nothing here is persisted or accepted from callers as trusted geometry.
use crate::{profile, Body, EvaluatedProfile, Model};
use std::collections::{BTreeMap, BTreeSet};

#[derive(Default)]
pub(super) struct Geometry {
    pub evaluated: BTreeMap<String, Body>,
    pub profiles: BTreeMap<String, profile::Profile>,
    pub consumed: BTreeSet<String>,
    // Consumption immediately before each feature, followed by the final state.
    pub checkpoints: Vec<BTreeSet<String>>,
}
impl Geometry {
    pub fn retain_prefix(mut self, before: &Model, after: &Model) -> (Self, usize) {
        let count = before
            .features
            .iter()
            .zip(&after.features)
            .take_while(|(a, b)| {
                a == b
                    && a.links()
                        .parameters
                        .iter()
                        .all(|id| before.parameters.get(id) == after.parameters.get(id))
            })
            .count();
        let retained: BTreeSet<_> = after.features[..count].iter().map(|f| f.id()).collect();
        self.evaluated
            .retain(|id, _| retained.contains(id.as_str()));
        self.profiles.retain(|id, _| retained.contains(id.as_str()));
        self.consumed = self.checkpoints[count].clone();
        // The suffix evaluator records the boundary checkpoint itself.
        self.checkpoints.truncate(count);
        (self, count)
    }
    pub fn into_parts(self) -> (Vec<Body>, Vec<EvaluatedProfile>) {
        let bodies = self
            .evaluated
            .into_iter()
            .filter(|(id, _)| !self.consumed.contains(id))
            .map(|(_, v)| v)
            .collect();
        (
            bodies,
            self.profiles.into_values().map(|p| p.output()).collect(),
        )
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{evaluate_geometry, evaluate_with_reuse, Request};
    use serde_json::{json, Value};

    fn request(model: &Model, operations: Value) -> Value {
        json!({"schema_version":1,"model":model,"operations":operations,"preserve":[]})
    }
    fn compare(value: Value) {
        let run = |reuse| {
            let r: Request = serde_json::from_value(value.clone()).unwrap();
            match evaluate_with_reuse(r, reuse) {
                Ok(v) => json!({"result":v}),
                Err(e) => json!({"error":e}),
            }
        };
        assert_eq!(run(true), run(false), "request: {value}");
    }
    fn fixture() -> Model {
        serde_json::from_str(include_str!(
            "../../../examples/ai-cad/linked-instances/cavity_copy.model.json"
        ))
        .unwrap()
    }
    #[test]
    fn retained_prefix_preserves_consumed_history_and_invalidates_at_first_change() {
        let before = fixture();
        let geometry = evaluate_geometry(&before).unwrap();
        let n = before.features.len();
        let (all, count) = geometry.retain_prefix(&before, &before);
        assert_eq!(count, n);
        assert_eq!(all.checkpoints.len(), n);
        let mut after = before.clone();
        after.features.pop();
        let (shorter, count) = evaluate_geometry(&before)
            .unwrap()
            .retain_prefix(&before, &after);
        assert_eq!(count, n - 1);
        // A removed suffix must not leave its consumption marks in the prefix.
        assert_eq!(
            shorter.consumed,
            evaluate_geometry(&after).unwrap().consumed
        );
        let last_parameter = before.features.last().unwrap().links().parameters[0].clone();
        after = before.clone();
        after.parameters.insert(last_parameter, "1/7".into());
        let (_, count) = evaluate_geometry(&before)
            .unwrap()
            .retain_prefix(&before, &after);
        assert_eq!(count, n - 1);
        after.parameters.insert("a.height".into(), "11".into());
        let (_, count) = evaluate_geometry(&before)
            .unwrap()
            .retain_prefix(&before, &after);
        assert_eq!(count, 1);
    }
    #[test]
    fn removed_consumers_restore_sources_and_shared_relations_rebuild() {
        let mut before = fixture();
        before.features.pop(); // Remove the linked copy, leaving the consuming Boolean last.
        let mut after = before.clone();
        let removed = after.features.pop().unwrap();
        let (state, count) = evaluate_geometry(&before)
            .unwrap()
            .retain_prefix(&before, &after);
        assert_eq!(count, after.features.len());
        assert_eq!(state.consumed, evaluate_geometry(&after).unwrap().consumed);
        compare(request(
            &before,
            json!([{"op":"remove_feature","id":removed.id()}]),
        ));
        // A cached prefix still owns its consumed inputs; an added second consumer rejects.
        compare(request(
            &before,
            json!([{"op":"add_feature","feature":{"kind":"translate","id":"extra","input":"a","offset":["a.c0","a.c0","a.c0"]}}]),
        ));
        compare(request(
            &before,
            json!([{"op":"set_relation","id":"b.height","relation":{"offset_mm":"-4","terms":{"a.height":"1"}}},{"op":"set_parameter","id":"a.height","mm":"12"}]),
        ));
        compare(request(
            &before,
            json!([{"op":"set_relation","id":"b.height","relation":{"offset_mm":"0","terms":{"b.height":"1"}}}]),
        ));
        // Constraints/global schema must be checked even with an entirely unchanged geometry prefix.
        compare(request(
            &before,
            json!([{"op":"fix_parameter","id":"a.height"}]),
        ));
        let mut invalid_fixed = before.clone();
        invalid_fixed.fixed.insert("a.height".into(), "11".into());
        compare(request(&invalid_fixed, json!([])));
    }
    #[test]
    fn cached_and_full_rebuild_match_corpus_inspection_and_parameter_edits() {
        let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../../examples/ai-cad");
        let mut cases = 0;
        for directory in std::fs::read_dir(root).unwrap() {
            let directory = directory.unwrap().path();
            if !directory.is_dir() {
                continue;
            }
            for path in std::fs::read_dir(directory).unwrap() {
                let path = path.unwrap().path();
                if !path.to_string_lossy().ends_with(".model.json") {
                    continue;
                }
                let model: Model = serde_json::from_slice(&std::fs::read(path).unwrap()).unwrap();
                compare(request(&model, json!([])));
                // Distinct positive/zero edits exercise both valid and rejected suffixes.
                for id in model
                    .parameters
                    .keys()
                    .take(1)
                    .chain(model.parameters.keys().rev().take(1))
                {
                    for mm in ["0", "7/3"] {
                        compare(request(
                            &model,
                            json!([{"op":"set_parameter","id":id,"mm":mm}]),
                        ));
                    }
                }
                cases += 1;
            }
        }
        assert!(
            cases >= 60,
            "Retain broad geometry corpus coverage: {cases}"
        );
    }
    #[test]
    fn structural_constraints_and_atomic_failures_match_full_rebuild() {
        let model = fixture();
        let last = model.features.last().unwrap();
        let first = &model.features[0];
        for operations in [
            json!([{"op":"remove_feature","id":last.id()}]),
            json!([{"op":"remove_feature","id":first.id()}]),
            json!([{"op":"add_feature","feature":{"kind":"translate","id":"extra","input":"result","offset":["a.c0","a.c0","a.c0"]}}]),
            json!([{"op":"fix_parameter","id":"a.height"},{"op":"set_parameter","id":"a.height","mm":"11"}]),
            json!([{"op":"remove_parameter","id":"a.height"}]),
            json!([{"op":"remove_feature","id":last.id()},{"op":"add_feature","feature":last}]),
        ] {
            compare(request(&model, operations));
        }
        // Reordering or changing the kind of a retained ID cannot reuse its geometry.
        let mut reordered = model.clone();
        reordered.features.swap(0, 1);
        assert_eq!(
            evaluate_geometry(&model)
                .unwrap()
                .retain_prefix(&model, &reordered)
                .1,
            0
        );
        // Even an operation that repairs an invalid starting model must reject it.
        let mut invalid = model.clone();
        invalid.parameters.insert("a.height".into(), "0".into());
        compare(request(
            &invalid,
            json!([{"op":"set_parameter","id":"a.height","mm":"10"}]),
        ));
        let mut guarded = request(
            &model,
            json!([{"op":"set_parameter","id":"a.height","mm":"11"}]),
        );
        guarded["preserve"] = json!(["a.height"]);
        compare(guarded);
    }
}
