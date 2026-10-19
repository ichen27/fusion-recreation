// Preview jobs never commit. The returned revision remains the commit precondition.
export async function previewJob(
  command,
  { request, pause, onStatus, isCancelled = () => false },
) {
  let job = await request("/api/preview-jobs", command);
  while (true) {
    onStatus(job);
    if (["succeeded", "failed", "cancelled"].includes(job.status)) {
      if (job.status === "succeeded" && isCancelled())
        throw Error(
          "preview_cancelled: Preview discarded; saved model is unchanged",
        );
      if (job.reply?.error)
        throw Error(`${job.reply.error.code}: ${job.reply.error.message}`);
      if (job.status !== "succeeded" || !job.reply?.result)
        throw Error("Preview finished without a result");
      return job.reply.result;
    }
    if (!["queued", "running", "cancelling"].includes(job.status))
      throw Error("Unknown preview job state");
    await pause(200);
    job = await request(
      `/api/preview-jobs?id=${encodeURIComponent(job.job_id)}`,
    );
  }
}
