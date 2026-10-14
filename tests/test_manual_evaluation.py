"""Offline checks for score integrity and large checkpoint download behavior."""
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'remote_challenge_evaluation'))
import manual


class ManualEvaluationTests(unittest.TestCase):
    def test_rate_and_invalid_trial_counts(self):
        self.assertEqual(manual.build_result(18, 20)[0]['accuracies'][manual.METRIC], 90)
        self.assertEqual(manual.build_result(0, 20)[0]['accuracies'][manual.METRIC], 0)
        self.assertEqual(manual.build_result(20, 20)[0]['accuracies'][manual.METRIC], 100)
        for counts in [(1, 0), (21, 20), (-1, 20), (1.5, 20), (True, 20)]:
            with self.assertRaises(ValueError):
                manual.build_result(*counts)

    def test_preview_does_not_access_evalai(self):
        with patch('manual.EvalAI_Interface') as client, patch('builtins.print'):
            manual.main(['--challenge-id','1','--phase-id','2','--submission-id','3',
                         'publish','--successful-trials','18','--total-trials','20',
                         '--protocol-version','v1'])
        client.assert_not_called()

    def test_wrong_phase_cannot_be_used(self):
        client = Mock()
        client.get_submission_by_pk.return_value = {'id': 3, 'challenge_phase': 4}
        with self.assertRaises(ValueError):
            manual.verified_submission(client, 3, 2)
        client.make_request.assert_not_called()

    def test_verified_publication_uses_counts_not_self_report(self):
        client = Mock()
        submission = {'id': 3, 'challenge_phase': 2, 'status':'submitted',
                      'submission_meta_attributes': {'Reported success rate (%) - unverified': '100'}}
        with patch.dict('os.environ', {'AUTH_TOKEN': 'fake', 'API_SERVER':'https://eval.ai'}), \
             patch('manual.EvalAI_Interface', return_value=client), \
             patch('manual.verified_submission', return_value=submission), patch('builtins.print'):
            manual.main(['--challenge-id','1','--phase-id','2','--submission-id','3',
                         'publish','--successful-trials','18','--total-trials','20',
                         '--protocol-version','v1','--apply'])
        payload = client.update_submission_data.call_args.args[0]
        self.assertEqual(json.loads(payload['result'])[0]['accuracies'][manual.METRIC], 90)
        self.assertEqual(payload['submission_status'], 'FINISHED')

    def test_finished_score_not_overwritten(self):
        client = Mock()
        with patch.dict('os.environ', {'AUTH_TOKEN': 'fake'}), \
             patch('manual.EvalAI_Interface', return_value=client), \
             patch('manual.verified_submission', return_value={'status':'finished'}), patch('builtins.print'):
            with self.assertRaises(ValueError):
                manual.main(['--challenge-id','1','--phase-id','2','--submission-id','3',
                             'publish','--successful-trials','18','--total-trials','20',
                             '--protocol-version','v1','--apply'])
        client.update_submission_data.assert_not_called()

    def test_streamed_download_and_incomplete_download_cleanup(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w') as archive:
            archive.writestr('README.md', 'example package')
        data = buffer.getvalue()
        submission = {'id':3, 'challenge_phase':2, 'input_file':'https://storage.example/file.zip'}
        for incomplete in (False, True):
            response = Mock()
            response.__enter__ = Mock(return_value=response)
            response.__exit__ = Mock(return_value=False)
            response.headers = {'Content-Length': str(len(data) + int(incomplete))}
            response.iter_content.return_value = [data[:10], data[10:]]
            with tempfile.TemporaryDirectory() as tmp, patch('manual.requests.get', return_value=response) as get:
                if incomplete:
                    with self.assertRaises(ValueError):
                        manual.download_checkpoint(submission, tmp)
                    self.assertFalse(list(Path(tmp).iterdir()))
                else:
                    manifest = manual.download_checkpoint(submission, tmp)
                    self.assertEqual(manifest['size_bytes'], len(data))
                    self.assertEqual((Path(tmp) / 'submission-3.zip').read_bytes(), data)
                    with self.assertRaises(ValueError):
                        manual.download_checkpoint(submission, tmp)
                self.assertTrue(get.call_args.kwargs['stream'])
                self.assertNotIn('Authorization', get.call_args.kwargs['headers'])


if __name__ == '__main__':
    unittest.main()
