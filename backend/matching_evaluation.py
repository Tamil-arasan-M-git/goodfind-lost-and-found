"""Small synthetic comparison set for matching-regression review.

This file deliberately contains no production reports or personal data.  It is
not a measure of real-world accuracy; it only checks expected ordering and
threshold behavior for representative wording and hard-negative examples.
"""

from difflib import SequenceMatcher

from matching import MATCH_THRESHOLD, calculate_match_score, date_similarity, detection_label_similarity


def _report(name, category="accessories", description="", location="library", item_date="2026-10-20", labels=None):
    return {"item_name": name, "category": category, "description": description,
            "location": location, "item_date": item_date, "detection_labels": labels or []}


def baseline_score(lost, found):
    """The pre-upgrade source formula, retained only for this synthetic comparison."""
    text = lambda first, second: SequenceMatcher(None, (first or "").lower().strip(), (second or "").lower().strip()).ratio() if first and second else 0.0
    category = 1.0 if (lost["category"] or "").lower().strip() == (found["category"] or "").lower().strip() else 0.0
    score = (category * .19 + text(lost["item_name"], found["item_name"]) * .43 +
             text(lost["description"], found["description"]) * .14 + text(lost["location"], found["location"]) * .095 +
             date_similarity(lost["item_date"], found["item_date"]) * .095 +
             detection_label_similarity(lost.get("detection_labels"), found.get("detection_labels")) * .05)
    if text(lost["item_name"], found["item_name"]) < .25:
        score *= .5
    return round(score * 100, 2)


CASES = [
    ("case and punctuation positive", _report("Black Leather Wallet", description="small gold logo", labels=["wallet_purse"]), _report(" black, leather wallet ", description="Small gold logo", labels=["wallet_purse"]), True),
    ("wallet wording positive", _report("black wallet", description="leather"), _report("black purse", description="leather"), True),
    ("phone wording positive", _report("mobile phone", category="electronics", description="black case"), _report("smartphone", category="electronics", description="black case"), True),
    ("different colours hard negative", _report("blue backpack", description="blue canvas backpack", labels=["backpack_bag"]), _report("red backpack", description="red canvas backpack", labels=["backpack_bag"]), False),
    ("different item types hard negative", _report("black wallet", description="leather"), _report("black water bottle", description="metal", labels=["water_bottle"]), False),
    ("missing evidence negative", _report("", category="", location="", item_date=None), _report("", category="", location="", item_date=None), False),
]


def evaluate():
    rows = []
    for label, lost, found, expected in CASES:
        old, new = baseline_score(lost, found), calculate_match_score(lost, found)
        rows.append({"case": label, "expected": expected, "baseline": old, "improved": new,
                     "baseline_returned": old >= MATCH_THRESHOLD, "improved_returned": new >= MATCH_THRESHOLD})
    return rows


if __name__ == "__main__":
    for result in evaluate():
        print("{case}: baseline={baseline:.2f}, improved={improved:.2f}, expected_returned={expected}, improved_returned={improved_returned}".format(**result))
