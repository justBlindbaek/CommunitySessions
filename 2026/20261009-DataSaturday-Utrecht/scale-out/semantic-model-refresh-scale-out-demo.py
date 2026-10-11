# %% [markdown]
# # Semantic Model Refresh Scale-Out – demo
#
# Shows how to use semantic model (query) scale-out to reduce the memory needed to refresh
# a semantic model in Microsoft Fabric / Power BI Premium.
#
# Normally a full refresh keeps the old copy of the data in memory while the new copy is built,
# which can roughly double the memory needed. With scale-out and auto sync turned off, report
# users are served by the read-only replica. That means you can:
#
#   1. empty the read-write replica with a `clearValues` refresh (frees its memory),
#   2. run a full refresh on the now empty read-write replica,
#   3. sync the read-write replica to the read-only replica when you are ready.
#
# Users keep querying the old data the whole time and never see an empty model.
#
# Blog post: https://justb.dk/blog/2026/03/using-semantic-model-scale-out-to-reduce-refresh-memory-in-fabric/
# Session:   "Breaking the Limits: Advanced Optimization of Semantic Models in Microsoft Fabric"
#            https://sessionize.com/s/justB/breaking-the-limits-advanced-optimization-of-seman/169980
#
# ⚠ WARNING: Only run this against a demo or test model. Step 0 changes the model's scale-out
#   settings and Step 1 empties the model. Run the Reset cell at the end to restore the settings.
#
# Prerequisites
#   - The model is on a Fabric (F SKU) or Power BI Premium capacity
#   - The model uses the large semantic model storage format
#   - You have write access to the model (changing scale-out settings may require being the owner)
#   - Python 3.10+ and the Fabric CLI: `pip install ms-fabric-cli`, then sign in with `fab auth login`
#
# How to run
#   Open this file in VS Code with the Python and Jupyter extensions. Fill in WORKSPACE_ID and
#   DATASET_ID in the Setup cell, then run one cell at a time with **Run Cell** (Shift+Enter).
#   Run the Setup cell first.
#
# | Step | What                | GUI alternative                                  |
# |------|---------------------|--------------------------------------------------|
# | -    | Check status        | Model settings > Query scale-out                 |
# | 0    | Enable Scale-Out    | Model settings > Query scale-out (auto sync off) |
# | 1    | clearValues         | -                                                |
# | 2    | Full Refresh        | Refresh now in the workspace                     |
# | 3    | Observe Out-of-Sync | -                                                |
# | 4    | Trigger Sync        | -                                                |
# | 5    | Verify Alignment    | -                                                |
# | -    | Reset (disable)     | Model settings > Query scale-out: Off            |
#
# In production you would chain steps 1, 2 and 4 in a pipeline or notebook. Remember that with
# auto sync off, report users don't see new data until you trigger the sync.

# %% Setup
import json
import shlex
import subprocess
import time

# Find both IDs in the URL of the semantic model in the Fabric portal:
# https://app.fabric.microsoft.com/groups/<WORKSPACE_ID>/datasets/<DATASET_ID>/details
WORKSPACE_ID = "<your-workspace-id>"
DATASET_ID = "<your-semantic-model-id>"
DATASET = f"groups/{WORKSPACE_ID}/datasets/{DATASET_ID}"


def fab(endpoint, method="get", body=None, params=None):
    """Call the Power BI REST API through the Fabric CLI and return the response body."""
    cmd = ["fab", "api", "-A", "powerbi", endpoint, "-X", method, "--output_format", "json"]
    if body:
        cmd += ["-i", json.dumps(body)]
    if params:
        cmd += ["-P", params]
    print(">", " ".join(shlex.quote(c) for c in cmd if c not in ("--output_format", "json")))
    out = subprocess.run(cmd, capture_output=True, text=True)
    try:
        response = json.loads(out.stdout)["result"]["data"][0]
    except (json.JSONDecodeError, KeyError, IndexError):
        print(out.stdout or out.stderr)
        raise
    print(f"  HTTP {response.get('status_code')}")
    return response.get("text")


def show_settings():
    ds = fab(DATASET)
    print(f"\nModel: {ds['name']}")
    settings = ds.get("queryScaleOutSettings", {})
    print(json.dumps(settings, indent=2))
    enabled = settings.get("maxReadOnlyReplicas", 0) != 0  # 0 = off, -1 = automatic, >0 = max replicas
    auto_sync = "ON" if settings.get("autoSyncReadOnlyReplicas", True) else "OFF"
    print(f"\n>>> Scale-out {'ENABLED' if enabled else 'DISABLED'}, auto sync {auto_sync}")


def show_sync_status():
    s = fab(f"{DATASET}/queryScaleOut/syncStatus")
    print(f"\nScale-out status : {s['scaleOutStatus']}")
    print(f"Last sync        : {s.get('syncStartTime')} -> {s.get('syncEndTime')} ({s.get('triggerReason')})")
    print(f"\n{'Replica':<8} {'Type':<10} {'Data timestamp'}")
    for r in s.get("scaleOutReplicas", []):
        print(f"{r['replicaId']:<8} {r['replicaType']:<10} {r['replicaTimestamp']}")
    in_sync = s["commitVersion"] == s["minActiveReadVersion"]
    print("\n" + (">>> IN SYNC - replicas aligned" if in_sync else ">>> OUT OF SYNC - replicas diverged"))
    return s


def latest_refresh():
    """Return the most recent refresh in the refresh history, or None if the model was never refreshed."""
    history = fab(f"{DATASET}/refreshes", params="$top=1").get("value") or []
    return history[0] if history else None


def refresh(body, poll_seconds=5):
    """Start an enhanced refresh and wait until it has finished."""
    previous = latest_refresh()
    previous_id = previous["requestId"] if previous else None
    fab(f"{DATASET}/refreshes", method="post", body=body)
    while True:
        time.sleep(poll_seconds)
        latest = latest_refresh()
        if latest is None or latest["requestId"] == previous_id:
            continue  # new refresh not registered yet
        print(f"  {latest['status']} (started {latest['startTime']})")
        if latest["status"] == "Unknown":  # "Unknown" = still running
            continue
        if latest["status"] != "Completed":
            raise RuntimeError(
                f"Refresh ended with status '{latest['status']}'. Stop here and check the refresh "
                f"history in the Fabric portal before running the next step.\n"
                f"{latest.get('serviceExceptionJson', '')}"
            )
        return latest


def wait_for_sync(poll_seconds=3):
    while True:
        time.sleep(poll_seconds)
        s = fab(f"{DATASET}/queryScaleOut/syncStatus")
        if s["commitVersion"] == s["minActiveReadVersion"]:
            print("  sync finished")
            return


# %% Check – is scale-out enabled?   (GUI: Model settings > Query scale-out)
show_settings()

# %% Step 0 – Enable Scale-Out, disable auto sync   (GUI: Model settings > Query scale-out)
fab(DATASET, method="patch", body={
    "queryScaleOutSettings": {"autoSyncReadOnlyReplicas": False, "maxReadOnlyReplicas": 1}
})
show_settings()

# %% Step 1 – clearValues: empty the read-write replica
refresh({"type": "clearValues", "commitMode": "transactional"})
# SHOW: report still shows the old refresh time - users are served by the read-only replica,
#       so they never see the emptied model.

# %% Step 2 – Full Refresh: rebuild the model   (GUI: Refresh now)
refresh({"type": "full", "commitMode": "transactional"})
# SHOW: report still shows the OLD refresh time, even though the model has just been refreshed.
# SHOW: open the semantic model in the workspace -> "This semantic model has pending updates"

# %% Step 3 – Observe: replicas have diverged
show_sync_status()
# The read-write replica has a newer data timestamp than the read-only replica.

# %% Step 4 – Trigger Sync
fab(f"{DATASET}/queryScaleOut/sync", method="post")
wait_for_sync()

# %% Step 5 – Verify alignment
show_sync_status()
# SHOW: reload the report -> new refresh time. The "pending updates" message is gone.

# %% Reset – disable scale-out and turn auto sync back on
fab(DATASET, method="patch", body={
    "queryScaleOutSettings": {"autoSyncReadOnlyReplicas": True, "maxReadOnlyReplicas": 0}
})
show_settings()

# %%
