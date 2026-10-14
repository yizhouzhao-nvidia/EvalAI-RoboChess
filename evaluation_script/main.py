"""RoboChess uses organizer-run local evaluation."""


def evaluate(test_annotation_file, user_submission_file, phase_codename, **kwargs):
    raise RuntimeError(
        "Manual local evaluation required. Download the checkpoint and publish "
        "verified trial counts with remote_challenge_evaluation/manual.py."
    )
