from __future__ import annotations

from collections import Counter, defaultdict
from itertools import combinations
from typing import Any


class AgreementMetricsService:
    def compute(
        self,
        ratings: list[dict[str, Any]],
        *,
        primary_rater_id: str | None = None,
        secondary_rater_id: str | None = None,
    ) -> dict[str, Any]:
        normalized = [
            {
                "item_id": str(rating["item_id"]).strip(),
                "rater_id": str(rating["rater_id"]).strip(),
                "label": str(rating["label"]).strip(),
            }
            for rating in ratings
        ]
        if primary_rater_id and secondary_rater_id:
            pairwise = self._cohens_kappa(
                normalized,
                primary_rater_id=primary_rater_id,
                secondary_rater_id=secondary_rater_id,
            )
        else:
            pairwise = None

        alpha = self._krippendorff_alpha_nominal(normalized)
        return {
            "cohens_kappa": pairwise,
            "krippendorff_alpha": alpha,
            "metadata": {
                "rating_count": len(normalized),
                "item_count": len({rating["item_id"] for rating in normalized}),
                "rater_count": len({rating["rater_id"] for rating in normalized}),
                "labels": sorted({rating["label"] for rating in normalized}),
            },
        }

    def _cohens_kappa(
        self,
        ratings: list[dict[str, str]],
        *,
        primary_rater_id: str,
        secondary_rater_id: str,
    ) -> dict[str, Any]:
        by_item: dict[str, dict[str, str]] = defaultdict(dict)
        for rating in ratings:
            if rating["rater_id"] in {primary_rater_id, secondary_rater_id}:
                by_item[rating["item_id"]][rating["rater_id"]] = rating["label"]

        pairs = [
            (
                item_ratings[primary_rater_id],
                item_ratings[secondary_rater_id],
            )
            for item_ratings in by_item.values()
            if primary_rater_id in item_ratings and secondary_rater_id in item_ratings
        ]
        n = len(pairs)
        if n == 0:
            return {
                "value": None,
                "status": "insufficient_overlap",
                "overlap_count": 0,
                "observed_agreement": None,
                "expected_agreement": None,
            }

        observed = sum(1 for left, right in pairs if left == right) / n
        primary_counts = Counter(left for left, _ in pairs)
        secondary_counts = Counter(right for _, right in pairs)
        labels = set(primary_counts) | set(secondary_counts)
        expected = sum(
            (primary_counts[label] / n) * (secondary_counts[label] / n)
            for label in labels
        )
        if expected == 1:
            value = 1.0 if observed == 1 else None
        else:
            value = (observed - expected) / (1 - expected)
        return {
            "value": round(value, 6) if value is not None else None,
            "status": "ok" if value is not None else "undefined",
            "overlap_count": n,
            "observed_agreement": round(observed, 6),
            "expected_agreement": round(expected, 6),
            "raters": [primary_rater_id, secondary_rater_id],
        }

    def _krippendorff_alpha_nominal(self, ratings: list[dict[str, str]]) -> dict[str, Any]:
        by_item: dict[str, list[str]] = defaultdict(list)
        for rating in ratings:
            by_item[rating["item_id"]].append(rating["label"])

        pair_disagreements = 0
        pair_count = 0
        for labels in by_item.values():
            if len(labels) < 2:
                continue
            for left, right in combinations(labels, 2):
                pair_count += 1
                if left != right:
                    pair_disagreements += 1

        if pair_count == 0:
            return {
                "value": None,
                "status": "insufficient_overlap",
                "unit_pair_count": 0,
                "observed_disagreement": None,
                "expected_disagreement": None,
            }

        observed_disagreement = pair_disagreements / pair_count
        label_counts = Counter(rating["label"] for rating in ratings)
        total = sum(label_counts.values())
        expected_disagreement = 1 - sum((count / total) ** 2 for count in label_counts.values())
        if expected_disagreement == 0:
            value = 1.0 if observed_disagreement == 0 else None
        else:
            value = 1 - (observed_disagreement / expected_disagreement)

        return {
            "value": round(value, 6) if value is not None else None,
            "status": "ok" if value is not None else "undefined",
            "unit_pair_count": pair_count,
            "observed_disagreement": round(observed_disagreement, 6),
            "expected_disagreement": round(expected_disagreement, 6),
        }
