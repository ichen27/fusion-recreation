import test from "node:test";
import assert from "node:assert/strict";
import { previewJob } from "./web/preview-client.mjs";

test("queued/running preview returns the snapshot revision and never sends a commit", async () => {
  const statuses = [],
    calls = [],
    result = { revision: 4, preview: true };
  const replies = [
    { job_id: "id", status: "queued", revision: 4 },
    { job_id: "id", status: "running", revision: 4 },
    { job_id: "id", status: "succeeded", revision: 4, reply: { result } },
  ];
  const command = {
    action: "preview",
    expected_revision: 4,
    operations: [],
    preserve: [],
  };
  const actual = await previewJob(command, {
    request: async (path, body) => {
      calls.push([path, body]);
      return replies.shift();
    },
    pause: async (ms) => assert.equal(ms, 200),
    onStatus: (job) => statuses.push(job.status),
  });
  assert.deepEqual(actual, result);
  assert.deepEqual(statuses, ["queued", "running", "succeeded"]);
  assert.deepEqual(calls[0], ["/api/preview-jobs", command]);
  assert.deepEqual(calls.slice(1), [
    ["/api/preview-jobs?id=id", undefined],
    ["/api/preview-jobs?id=id", undefined],
  ]);
});

test("cancellation, geometry errors and expired jobs cannot become a preview", async () => {
  for (const status of ["cancelled", "failed"]) {
    await assert.rejects(
      previewJob(
        {},
        {
          request: async () => ({
            job_id: "id",
            status,
            reply: { error: { code: status, message: "unchanged" } },
          }),
          pause: async () => {},
          onStatus: () => {},
        },
      ),
      new RegExp(status),
    );
  }
  await assert.rejects(
    previewJob(
      {},
      {
        request: async () => {
          throw Error("missing_job: expired");
        },
        pause: async () => {},
        onStatus: () => {},
      },
    ),
    /missing_job/,
  );
});

test("a cancellation arriving after server completion still discards the preview", async () => {
  let cancelled = false;
  await assert.rejects(
    previewJob(
      {},
      {
        request: async () => ({
          job_id: "id",
          status: "succeeded",
          reply: { result: { revision: 1 } },
        }),
        pause: async () => {},
        onStatus: () => {
          cancelled = true;
        },
        isCancelled: () => cancelled,
      },
    ),
    /preview_cancelled/,
  );
});
