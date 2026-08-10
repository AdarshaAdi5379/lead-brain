from __future__ import annotations

import logging
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import main as pipeline_module
from src.enrichment.config import EnrichmentConfig
from src.enrichment.report import EnrichmentReport

from tests.enrichment_fixtures import seed


def _config(enabled: bool = True) -> EnrichmentConfig:
    return EnrichmentConfig(enabled=enabled)


def _args(*, no_crawl: bool = False, no_enrichment: bool = False) -> SimpleNamespace:
    return SimpleNamespace(no_crawl=no_crawl, no_enrichment=no_enrichment)


class TestEnrichSeedsPass(unittest.TestCase):
    def test_no_crawl_skips_enrichment(self) -> None:
        seeds = [seed()]
        with patch.object(pipeline_module, "run_enrichment") as run:
            out = pipeline_module._enrich_seeds_pass(None, None, seeds, _args(no_crawl=True))
        self.assertEqual(out, seeds)
        run.assert_not_called()

    def test_no_enrichment_skips_enrichment(self) -> None:
        seeds = [seed()]
        with patch.object(pipeline_module, "run_enrichment") as run:
            out = pipeline_module._enrich_seeds_pass(None, None, seeds, _args(no_enrichment=True))
        self.assertEqual(out, seeds)
        run.assert_not_called()

    def test_disabled_config_skips_enrichment(self) -> None:
        seeds = [seed()]
        with (
            patch.object(pipeline_module, "run_enrichment") as run,
            patch.object(
                pipeline_module,
                "enrichment_config_from_settings",
                return_value=_config(enabled=False),
            ),
        ):
            out = pipeline_module._enrich_seeds_pass(None, None, seeds, _args())
        self.assertEqual(out, seeds)
        run.assert_not_called()

    def test_enabled_runs_and_logs_summary(self) -> None:
        seeds = [seed()]
        replaced = [seed(business_name="Replaced")]

        def fake_run(connection, s, config, logger=None):
            return replaced, EnrichmentReport(processed=1, found=1)

        with (
            patch.object(pipeline_module, "run_enrichment", side_effect=fake_run) as run,
            patch.object(
                pipeline_module,
                "enrichment_config_from_settings",
                return_value=_config(enabled=True),
            ),
        ):
            with self.assertLogs(level="INFO") as logs:
                out = pipeline_module._enrich_seeds_pass(
                    None, logging.getLogger("test"), seeds, _args()
                )
        self.assertEqual(out, replaced)
        run.assert_called_once()
        self.assertTrue(any("Website enrichment:" in line for line in logs.output))


if __name__ == "__main__":
    unittest.main()