"""Only aggregate data may leave the administrative summary exporter."""

from copy import deepcopy
import unittest
from unittest.mock import patch

from scripts.export_usage_summary import fetch_summary, validate_summary


SUMMARY = {
    "schema_version": 1, "generated_at": "2026-09-29T12:00:00+00:00",
    "window_start": "2026-07-01T12:00:00+00:00", "retention_days": 90,
    "launches": 3, "distinct_installations": 2,
    "by_version": [{"version": "0.9.11", "launches": 3, "distinct_installations": 2}],
}


class ExportTests(unittest.TestCase):
    def test_valid_aggregate(self):
        self.assertEqual(validate_summary(SUMMARY), SUMMARY)

    def test_rejects_raw_id_fields_and_invalid_counts(self):
        for change in (
            {"installation_id": "private-id"}, {"launches": 4},
            {"distinct_installations": 4}, {"launches": True},
            {"generated_at": "2026-09-29"}, {"retention_days": 0},
            {"by_version": [SUMMARY["by_version"][0] | {"launch_id": "private-id"}]},
        ):
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_summary(deepcopy(SUMMARY) | change)

    def test_rejects_credential_or_non_https_urls_before_network(self):
        with patch("scripts.export_usage_summary.build_opener") as opener:
            for url in (
                "http://example.com/v1/summary", "https://user:pass@example.com/v1/summary",
                "https://example.com/v1/summary?token=x", "https://example.com/v1/summary#x",
            ):
                with self.subTest(url=url), self.assertRaises(ValueError):
                    fetch_summary(url, "x" * 32)
            opener.assert_not_called()


if __name__ == "__main__":
    unittest.main()
