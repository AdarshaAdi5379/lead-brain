"""Candidate URL normalization: reuse the pipeline URL normalizer and reject
social/directory/malformed candidates."""

from __future__ import annotations

import unittest

from src.enrichment.normalizer import clean_candidate_url, rejected_host


class TestCleanCandidateUrl(unittest.TestCase):
    def test_basic_url_survives(self) -> None:
        self.assertEqual(
            clean_candidate_url("https://radiantplumbing.com/"),
            "https://radiantplumbing.com/",
        )

    def test_tracking_params_stripped(self) -> None:
        self.assertEqual(
            clean_candidate_url(
                "https://radiantplumbing.com/?utm_source=ddg&utm_medium=organic&fbclid=abc"
            ),
            "https://radiantplumbing.com/",
        )

    def test_fragment_dropped(self) -> None:
        self.assertEqual(
            clean_candidate_url("https://radiantplumbing.com/#services"),
            "https://radiantplumbing.com/",
        )

    def test_http_upgraded_space(self) -> None:
        self.assertIsNotNone(clean_candidate_url("http://radiantplumbing.com"))

    def test_social_profiles_rejected(self) -> None:
        for url in (
            "https://facebook.com/radiantplumbing",
            "https://www.instagram.com/radiantplumbing",
            "https://www.linkedin.com/company/radiant",
            "https://twitter.com/radiant",
            "https://wa.me/15125550123",
        ):
            self.assertIsNone(clean_candidate_url(url), url)

    def test_directory_pages_rejected(self) -> None:
        for url in (
            "https://www.yelp.com/biz/radiant-plumbing-austin",
            "https://www.yellowpages.com/austin-tx/mip/radiant-plumbing",
            "https://www.bbb.org/us/tx/austin/profile/plumber/radiant-123",
            "https://www.thumbtack.com/tx/austin/radiant-plumbing",
        ):
            self.assertIsNone(clean_candidate_url(url), url)

    def test_malformed_rejected(self) -> None:
        self.assertIsNone(clean_candidate_url("radiant plumbing"))
        self.assertIsNone(clean_candidate_url("ftp://files.example.com/x"))
        self.assertIsNone(clean_candidate_url("javascript:alert(1)"))
        self.assertIsNone(clean_candidate_url(""))

    def test_rejected_host_heuristic(self) -> None:
        self.assertTrue(rejected_host("https://www.yelp.com/x"))
        self.assertTrue(rejected_host("https://sub.facebook.com/x"))
        self.assertFalse(rejected_host("https://radiantplumbing.com/x"))


if __name__ == "__main__":
    unittest.main()