import unittest

from tools import pg19_selected12_baseline as baseline


class Pg19Selected12BaselineTests(unittest.TestCase):
    def test_selected_samples_default_to_all_and_deduplicate(self):
        self.assertEqual(baseline.selected_samples(None), list(baseline.SAMPLES))
        sample = baseline.SAMPLES[0]
        self.assertEqual(baseline.selected_samples([sample, sample]), [sample])

    def test_paired_summary_reports_direction_and_interval(self):
        deltas = [1.0] * 6 + [-0.5] * 4 + [0.0] * 2
        result = baseline.paired_summary(deltas)
        self.assertEqual(result["count"], 12)
        self.assertEqual(result["candidate_wins"], 6)
        self.assertEqual(result["ties"], 2)
        self.assertEqual(result["baseline_wins"], 4)
        self.assertGreaterEqual(result["two_sided_exact_sign_test_p"], 0.0)
        self.assertLessEqual(result["two_sided_exact_sign_test_p"], 1.0)
        self.assertLess(result["mean_95_percent_ci"][0], result["mean"])
        self.assertGreater(result["mean_95_percent_ci"][1], result["mean"])

    def test_pairing_covers_all_frozen_samples(self):
        manifest = baseline.pairing_manifest()
        self.assertEqual(manifest["dataset_sha256"], baseline.file_sha256(baseline.DATASET))
        self.assertEqual(
            {row["sample_id"] for row in manifest["samples"]},
            set(baseline.SAMPLES),
        )


if __name__ == "__main__":
    unittest.main()
