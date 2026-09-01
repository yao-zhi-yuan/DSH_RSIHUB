from __future__ import annotations

import json
import unittest
from pathlib import Path

from scripts import build_visualization


FIXTURE = Path(__file__).resolve().parent / "fixtures" / "summary-sample.json"


class BuildVisualizationTests(unittest.TestCase):
    def _summary(self) -> dict:
        return build_visualization.load_summary(FIXTURE)

    def test_renders_self_contained_page(self) -> None:
        html = build_visualization.render_html(self._summary())
        self.assertIn("<!DOCTYPE html>", html)
        self.assertIn("score-chart", html)
        self.assertIn("gen-1", html)
        self.assertEqual(html.count("candidate-diff"), 3)
        self.assertNotIn("secret-value", html)

    def test_no_external_resources(self) -> None:
        html = build_visualization.render_html(self._summary())
        # A shareable offline page must not pull from a CDN or remote host.
        self.assertNotIn("http://", html)
        self.assertNotIn("https://", html)

    def test_contains_all_five_regions(self) -> None:
        html = build_visualization.render_html(self._summary())
        for region in (
            "score-chart",
            "generation-overview",
            "candidate-diff",
            "resource-consumption",
            "improvement-hypothesis",
        ):
            self.assertIn(region, html)

    def test_missing_key_raises_and_names_it(self) -> None:
        summary = self._summary()
        del summary["resources"]
        with self.assertRaises(build_visualization.VisualizationError) as caught:
            build_visualization.render_html(summary)
        self.assertIn("resources", str(caught.exception))

    def test_missing_nested_key_raises(self) -> None:
        summary = self._summary()
        del summary["generations"][0]["diff"]
        with self.assertRaises(build_visualization.VisualizationError) as caught:
            build_visualization.render_html(summary)
        self.assertIn("diff", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
