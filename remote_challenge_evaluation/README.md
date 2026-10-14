# RoboChess organizer workflow

EvalAI stores small ZIP submissions containing pinned model and code references
and inference instructions. Checkpoints stay on Hugging Face or another accessible
host. Organizers fetch the referenced artifacts, evaluate locally,
and publish verified pick-and-place scores. No always-on worker or robot connection
is required by this tool. Do not run the old automatic polling worker.

## Setup

```bash
python3 -m pip install -r remote_challenge_evaluation/requirements.txt
read -rs -p 'EvalAI host token: ' AUTH_TOKEN
export AUTH_TOKEN
export API_SERVER=https://eval.ai
```

Use a host account for the same server. Get the actual challenge, phase, and
submission IDs from EvalAI; YAML IDs are template IDs, not server IDs.

## Download a submission

```bash
python3 remote_challenge_evaluation/manual.py \
  --challenge-id 123 --phase-id 456 --submission-id 789 \
  download --output-dir local_submissions
```

The script verifies the submission belongs to the challenge's `pick_place` phase,
streams the ZIP to disk, and records its SHA-256 and size. It leaves the submission
status unchanged. Download retries restart from the beginning; resumable downloading
is not implemented. Files are never extracted and checkpoints are never executed
by this tool. It downloads only the instructions ZIP; it does not resolve links or
fetch external model weights. Review the instructions, then fetch the model and code
at the exact submitted revisions. Arrange access to private or gated repositories
separately; never put credentials in the ZIP. Review code before running it.
Use the default ignored `local_submissions/` directory; do not commit weights or
include them in the challenge configuration package.

## Evaluate locally

Use a consistent, published protocol for every participant. Record the successful
and total trials and protocol version. A success requires both pickup and placement.
The robot, target tolerances, initial conditions, time limit, and trial count must
be finalized in `annotations/pick_place_protocol.json` and the evaluation HTML.
The repository does not contain a robot runner; use your own evaluation setup.

## Preview and publish a score

```bash
python3 remote_challenge_evaluation/manual.py \
  --challenge-id 123 --phase-id 456 --submission-id 789 \
  publish --successful-trials 18 --total-trials 20 --protocol-version pick-place-v1
```

This prints a preview of the EvalAI result payload (90%) without a network request.
Repeat with `--apply` to send the result and mark the submission FINISHED. Trial
counts must be integers, total must be positive, and successes cannot exceed total.
The tool refuses to overwrite finished or cancelled submissions. It never uses
participant-reported metadata to compute the official score. Queue messages are
not consumed by this manual tool; a future remote worker must skip terminal
submissions rather than evaluating them again.

The API format follows the EvalAI remote-evaluation starter. Offline checks do not
confirm compatibility or permissions on the deployed EvalAI server: test one ZIP
download and one score publication on staging before launch.

## Linked model submissions

Participants upload a small ZIP with:

- A model repository URL, full immutable revision (e.g. Hugging Face commit hash),
  checkpoint filenames/shard index, and pinned references for all inference assets.
- A code repository URL and full commit hash, or code included in the ZIP.
- A README with download, setup, and inference commands plus observation/action interfaces.
- Pinned dependencies, runtime versions, memory requirements, parameter count, and precision.
- Licenses and access requirements; references must remain accessible throughout evaluation.

A branch name such as `main` or a mutable tag alone is insufficient. A new model or
code revision requires a new submission. Do not upload tokens or passwords.

3–32 billion parameters describes the model rather than the ZIP size. At FP16/BF16,
weights alone can occupy roughly 6–64 GB (decimal), so provision local disk and
memory accordingly. EvalAI stores the instructions ZIP rather than those weights.

Participants authenticate using their own token and run:

```bash
evalai challenge CHALLENGE_ID phase PHASE_ID submit --file submission.zip --public
```

An example instructions package is in `remote_challenge_evaluation/submission_example/`.
Replace all placeholders before zipping it. Organizers should record the downloaded
model/code revisions alongside local trial results. The current manual tool does
not fetch external models or validate the references automatically.

Participant-reported scores are optional text metadata, clearly labeled unverified.
They are not validated percentages or separate leaderboard entries. The official
leaderboard has only the organizer-verified success-rate metric. Private submissions
may require participant visibility changes before scores appear publicly; verify
this behavior on staging before promising a public ranking.

## Before launch

The challenge is deliberately `published: false`. Finalize the protocol, schedule,
submission limits, rules, and logo; the existing starter logo is retained. Current
start/end dates are provisional for a continuing benchmark, not the workshop
schedule. After staging validation and confirming linked artifact access, publish the challenge.

References:
- https://evalai.readthedocs.io/en/latest/02-for-challenge-hosts/evaluation/remote-evaluation.html
- https://cli.eval.ai/
