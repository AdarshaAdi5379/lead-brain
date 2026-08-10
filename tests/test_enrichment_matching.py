"""Deterministic candidate scoring: brand/location/phone/email signals,
confidence thresholding, and rejection of bad matches."""

from __future__ import annotations

import unittest

from src.enrichment.base import LeadContext
from src.enrichment.config import EnrichmentConfig, confidence_label
from src.enrichment.match import (
    brand_component,
    email_domain_candidate,
    score_candidate,
)

from tests.enrichment_fixtures import lead, matching_page


def _ctx(**overrides) -> LeadContext:
    return LeadContext(**lead(**overrides))


def _score(ctx: LeadContext, page, url: str = "https://radiantplumbing.com/"):
    return score_candidate(url, title=page.title, text=page.text, lead=ctx)


class TestBrandComponent(unittest.TestCase):
    def test_title_presence_strong(self) -> None:
        self.assertEqual(brand_component("Radiant Plumbing", "Radiant Plumbing - Austin TX", ""), 0.55)

    def test_body_only_majority_strong(self) -> None:
        self.assertEqual(
            brand_component("Radiant Plumbing", "", "the Radiant Plumbing guys do drains"), 0.55
        )

    def test_partial_body_weak_signal(self) -> None:
        self.assertEqual(
            brand_component("Radiant Plumbing", "", "our friends at Radiant services Austin"),
            0.30,
        )

    def test_no_brand_zero(self) -> None:
        self.assertEqual(brand_component("Radiant Plumbing", "Unrelated Page", "some other business"), 0.0)

    def test_single_token_name_needs_title_and_body(self) -> None:
        self.assertEqual(brand_component("Sparks", "", "Sparks electricians in Austin"), 0.0)
        self.assertEqual(
            brand_component("Sparks", "Sparks Electric", "Sparks electricians in Austin"), 0.55
        )


class TestScoreCandidate(unittest.TestCase):
    def test_strong_name_city_phone_high_confidence(self) -> None:
        ctx = _ctx()
        score, signals = _score(ctx, matching_page())
        self.assertEqual(signals["brand"], 0.55)
        self.assertEqual(signals["phone"], 0.35)
        self.assertEqual(signals["location"], 0.15)
        self.assertGreaterEqual(score, 0.75)

    def test_email_domain_match_high(self) -> None:
        ctx = _ctx(email="hello@radiantplumbing.com")
        score, signals = _score(ctx, matching_page())
        self.assertEqual(signals["email_domain"], 0.35)
        self.assertEqual(score, 1.0)

    def test_email_domain_mismatch_adds_nothing(self) -> None:
        ctx = _ctx(email="hello@otherplumbing.com")
        score, signals = _score(ctx, matching_page())
        self.assertEqual(signals["email_domain"], 0.0)
        self.assertGreaterEqual(score, 0.75)

    def test_wrong_phone_name_alone_stays_low(self) -> None:
        # Brand in the title but nothing else: no phone/email/location match.
        from tests.enrichment_fixtures import html_page

        page = html_page("Radiant Plumbing", "call (999) 888-7777 for service")
        score, signals = _score(_ctx(), page)
        self.assertEqual(signals["phone"], 0.0)
        self.assertEqual(signals["location"], 0.0)
        self.assertLess(score, 0.60)

    def test_unrelated_page_not_accepted(self) -> None:
        from tests.enrichment_fixtures import html_page

        # Contains only the industry word, never the actual brand tokens.
        page = html_page("Plumbing Parts Wholesale", "shipping warehouse parts")
        score, signals = _score(_ctx(), page)
        self.assertEqual(signals["brand"], 0.30)
        self.assertLess(score, 0.60)

    def test_fully_unrelated_page_scores_zero(self) -> None:
        from tests.enrichment_fixtures import html_page

        page = html_page("Warehouse Shipping Supplies", "boxes pallets freight")
        score, signals = _score(_ctx(), page)
        self.assertEqual(score, 0.0)
        self.assertEqual(signals["brand"], 0.0)

    def test_directory_style_page_low(self) -> None:
        # Correct phone + location but no brand name present.
        from tests.enrichment_fixtures import html_page

        page = html_page("Plumbers in Austin TX", "call (512) 555-0123 Austin Texas drain services")
        score, _ = _score(_ctx(), page)
        self.assertEqual(score, 0.0)


class TestEmailDomainCandidate(unittest.TestCase):
    def test_company_domain_produces_candidate(self) -> None:
        self.assertEqual(
            email_domain_candidate("hello@radiantplumbing.com"),
            "https://radiantplumbing.com",
        )

    def test_free_mailer_rejected(self) -> None:
        self.assertIsNone(email_domain_candidate("owner@gmail.com"))
        self.assertIsNone(email_domain_candidate("owner@yahoo.com"))
        self.assertIsNone(email_domain_candidate("owner@hotmail.com"))

    def test_missing_or_malformed_rejected(self) -> None:
        self.assertIsNone(email_domain_candidate(None))
        self.assertIsNone(email_domain_candidate("not-an-email"))
        self.assertIsNone(email_domain_candidate(""))


class TestConfidenceThresholding(unittest.TestCase):
    def setUp(self) -> None:
        self.config = EnrichmentConfig()

    def test_labels(self) -> None:
        self.assertEqual(confidence_label(0.80, self.config), "high")
        self.assertEqual(confidence_label(0.75, self.config), "high")
        self.assertEqual(confidence_label(0.65, self.config), "medium")
        self.assertEqual(confidence_label(0.59, self.config), "low")
        self.assertEqual(confidence_label(None, self.config), "low")

    def test_accept_threshold_applied_by_service(self) -> None:
        from src.enrichment.service import _best_verified

        ctx = _ctx()
        page = matching_page()
        score, _ = _score(ctx, page)
        self.assertGreaterEqual(score, self.config.accept_threshold)
        # A brand-only page (no validating evidence) must sit below the
        # accept threshold even when the brand name is in the title:
        from tests.enrichment_fixtures import html_page

        bare = html_page("Radiant Plumbing", "welcome to our website")
        score, _ = _score(ctx, bare)
        self.assertLess(score, self.config.accept_threshold)


if __name__ == "__main__":
    unittest.main()