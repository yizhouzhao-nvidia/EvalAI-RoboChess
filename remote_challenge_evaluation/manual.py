"""Download checkpoints and publish verified local trial results to EvalAI."""

import argparse
import hashlib
import json
import os
from pathlib import Path
from urllib.parse import urlparse
import zipfile

import requests

from eval_ai_interface import EvalAI_Interface

METRIC = "Pick-and-place success rate (%)"
SPLIT = "pick_place_split"


def build_result(successful, total):
    if type(successful) is not int or type(total) is not int:
        raise ValueError("Trial counts must be integers.")
    if total <= 0 or not 0 <= successful <= total:
        raise ValueError("Require total > 0 and 0 <= successful <= total.")
    return [{"split": SPLIT, "show_to_participant": True,
             "accuracies": {METRIC: 100.0 * successful / total}}]


def verified_submission(client, submission_id, phase_id):
    submission = client.get_submission_by_pk(submission_id)
    if submission.get("id") != submission_id or submission.get("challenge_phase") != phase_id:
        raise ValueError("Submission does not match the requested submission and phase IDs.")
    # Fetch the phase through a challenge-scoped endpoint to verify ownership.
    url = client.return_url_per_environment(
        f"/api/challenges/challenge/{client.CHALLENGE_PK}/challenge_phase/{phase_id}"
    )
    phase = client.make_request(url, "GET")
    if phase.get("id") != phase_id or phase.get("codename") != "pick_place":
        raise ValueError("Expected the pick_place phase of this challenge.")
    return submission


def download_checkpoint(submission, output_dir):
    """Stream to disk without loading weights, extracting, or executing code."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir / f"submission-{submission['id']}.zip"
    partial = destination.with_suffix(".zip.part")
    url = submission.get("input_file", "")
    if urlparse(url).scheme != "https":
        raise ValueError("Checkpoint download requires an HTTPS file URL.")
    if destination.exists():
        raise ValueError(f"Download already exists: {destination}")
    if partial.exists():
        raise ValueError(f"Partial download already exists: {partial}")
    created_partial = False
    digest = hashlib.sha256()
    size = 0
    try:
        # Storage URLs are signed; never forward the EvalAI auth token to storage.
        with requests.get(url, stream=True, timeout=(30, 300),
                          headers={"Accept-Encoding": "identity"}) as response:
            response.raise_for_status()
            with partial.open("xb") as handle:
                created_partial = True
                for chunk in response.iter_content(chunk_size=8 * 1024 * 1024):
                    if chunk:
                        handle.write(chunk)
                        digest.update(chunk)
                        size += len(chunk)
            expected = response.headers.get("Content-Length")
            if expected is not None and size != int(expected):
                raise ValueError("Download length does not match Content-Length.")
        if not zipfile.is_zipfile(partial):
            raise ValueError("Downloaded file is not a ZIP archive.")
        partial.rename(destination)
    except Exception:
        if created_partial:
            partial.unlink(missing_ok=True)
        raise
    manifest = {"submission_id": submission["id"],
                "phase_id": submission["challenge_phase"],
                "file": destination.name, "size_bytes": size,
                "sha256": digest.hexdigest()}
    destination.with_suffix(".manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--challenge-id", type=int, required=True,
                        help="Actual EvalAI ID, not the YAML template ID")
    parser.add_argument("--phase-id", type=int, required=True)
    parser.add_argument("--submission-id", type=int, required=True)
    sub = parser.add_subparsers(dest="command", required=True)
    download = sub.add_parser("download", help="Download a ZIP without changing submission status")
    download.add_argument("--output-dir", default="local_submissions")
    publish = sub.add_parser("publish", help="Preview or upload verified local results")
    publish.add_argument("--successful-trials", type=int, required=True)
    publish.add_argument("--total-trials", type=int, required=True)
    publish.add_argument("--protocol-version", required=True)
    publish.add_argument("--apply", action="store_true", help="Send the previewed score to EvalAI")
    args = parser.parse_args(argv)
    if min(args.challenge_id, args.phase_id, args.submission_id) <= 0:
        parser.error("EvalAI IDs must be positive integers.")

    payload = None
    if args.command == "publish":
        if not args.protocol_version.strip():
            parser.error("A nonempty protocol version is required.")
        result = build_result(args.successful_trials, args.total_trials)
        payload = {"challenge_phase": args.phase_id, "submission": args.submission_id,
                   "submission_status": "FINISHED", "result": json.dumps(result),
                   "stdout": (f"Organizer-verified: {args.successful_trials}/{args.total_trials} "
                              f"successful trials; protocol {args.protocol_version}."),
                   "stderr": "", "metadata": json.dumps({
                       "score_source": "organizer_verified",
                       "successful_trials": args.successful_trials,
                       "total_trials": args.total_trials,
                       "protocol_version": args.protocol_version})}
        print(json.dumps(payload, indent=2))
        if not args.apply:
            print("Preview only. Add --apply to publish after local evaluation.")
            return

    token = os.environ.get("AUTH_TOKEN", "").strip()
    server = os.environ.get("API_SERVER", "https://eval.ai").rstrip("/")
    if not token or urlparse(server).scheme != "https":
        parser.error("Set AUTH_TOKEN and use an HTTPS API_SERVER (default https://eval.ai).")
    client = EvalAI_Interface(token, server, "", args.challenge_id)
    submission = verified_submission(client, args.submission_id, args.phase_id)
    if args.command == "download":
        print(json.dumps(download_checkpoint(submission, args.output_dir), indent=2))
    else:
        if submission.get("status", "").lower() in {"finished", "cancelled"}:
            raise ValueError("Refusing to overwrite a finished or cancelled submission.")
        client.update_submission_data(payload)
        print("Verified score published to EvalAI.")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, requests.RequestException):
        # Request exceptions can expose signed storage URLs; omit them here.
        raise SystemExit("Operation failed. Check IDs, credentials, available disk space, ZIP file, and network; no automatic retry was made.")
