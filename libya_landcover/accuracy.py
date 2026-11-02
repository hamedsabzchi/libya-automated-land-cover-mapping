"""Read and present existing validation results. No EE, inference or job writes."""
from html import escape

from .jobs import checked_mapping_bundle


def saved_accuracy(store, job_id):
    reply = {"type": "accuracy", "state": "unavailable", "source": "saved_mapping_result",
             "scope": "model_validation", "job_id": job_id}
    if not job_id:
        return {**reply, "message": "No map is selected. Select a saved map or open your saved-work ZIP to read its recorded accuracy."}
    try:
        job = store.get(job_id)
        if job["kind"] in {"export", "assistant_snapshot"}:
            job = store.get(job["inputs"]["mapping_job_id"])
        if job["kind"] != "mapping":
            return {**reply, "message": "Select a map or one of its downloads to read the saved model accuracy."}
        reply["mapping_job_id"] = job["job_id"]
        if job["state"] != "completed":
            return {**reply, "mapping_state": job["state"], "message":
                    "Recorded accuracy is not available for this map yet (" + job["state"] + "). No new calculation was started."}
        checked = checked_mapping_bundle(store, job)
        result = checked["result"].to_dict()
        metrics = result["metrics"]
        # Reuse the reference presentation formula; no classifier re-evaluation.
        rows = checked["result"].class_table()
        for i, row in enumerate(rows):
            row.pop("status", None)  # Seed-search inclusion is not an accuracy verdict.
            if metrics["producer"][i] is None:
                row["producer_percent"] = None
            if sum(r[i] for r in metrics["confusion"]) == 0:
                row["user_percent"] = None
        return {**reply, "state": "available", "run_id": result["run_id"],
                "result_id": result["result_id"], "recorded_at": result["created_at"],
                "request": result["request"], "metrics": metrics, "classes": rows,
                "message": "These are the model validation results saved with this map. "
                "They are not a separate accuracy assessment of the selected tile. "
                "Reading this report does not call Earth Engine or rerun the model."}
    except (ValueError, KeyError, OSError, TypeError):
        return {**reply, "message": "The saved accuracy record could not be read or verified. "
                "Your existing work is unchanged. Open its original saved-work ZIP; no calculation was started."}


def render_accuracy(reply):
    def cell(value):
        return escape(str(value))

    def percent(value):
        return "Not available" if value is None else f"{value:.2f}%"

    def table(headers, rows):
        return ('<div style="overflow-x:auto"><table style="text-align:left;width:100%">'
                '<thead><tr>' + ''.join('<th style="padding:5px">' + cell(h) + '</th>' for h in headers) +
                '</tr></thead><tbody>' + ''.join('<tr>' + ''.join(
                    '<td style="padding:5px">' + cell(v) + '</td>' for v in row) + '</tr>' for row in rows) +
                '</tbody></table></div>')

    body = '<p>' + cell(reply.get("message", "")) + '</p>'
    if reply.get("state") != "available":
        return body
    from .chat_ui import area_name
    metrics = reply["metrics"]
    body = '<h4>Saved model accuracy · ' + cell(area_name(reply["request"])) + ' · ' + cell(reply["request"]["target_year"]) + '</h4>' + body
    body += table(["Measure", "Recorded result"], [
        ("Overall accuracy", percent(None if metrics["overall"] is None else metrics["overall"] * 100)),
        ("Kappa", "Not available" if metrics["kappa"] is None else f'{metrics["kappa"]:.4f}'),
        ("Validation samples", metrics["sampled_validation_count"])])
    body += '<h4>Accuracy by class</h4>'
    body += table(["Code", "Class", "Producer accuracy", "User accuracy", "Reference samples"],
                  [(r["code"], r["name"], percent(r["producer_percent"]), percent(r["user_percent"]), r["samples"])
                   for r in reply["classes"]])
    body += ('<p>Producer accuracy: how many reference samples of a class were identified correctly. '
             'User accuracy: how many samples predicted as a class match the reference. '
             'Not available means the stored measure is missing or has no predicted samples.</p>')
    body += '<details><summary>Confusion matrix</summary><p>Rows: reference classes. Columns: predicted classes. Codes match the table above.</p>'
    body += table(["Reference / predicted"] + list(range(1, 13)),
                  [[i + 1] + row for i, row in enumerate(metrics["confusion"])]) + '</details>'
    body += '<details><summary>Saved result source</summary>' + table(["Field", "Value"], [
        ("Recorded at", reply["recorded_at"]), ("Mapping job", reply["mapping_job_id"]),
        ("Run", reply["run_id"]), ("Result", reply["result_id"]),
        ("Boundary", reply["request"]["aoi_asset"]), ("Training data", reply["request"]["training_asset"])]) + '</details>'
    return body
