"""Corpus-specific text normalization for the reference papers."""

import re


def normalize_text(text):
    text = text.replace("B ́ezier", "Bézier").replace("B´ezier", "Bézier")
    text = text.replace("B ́etrisey", "Bétrisey").replace("B´etrisey", "Bétrisey")
    return text.replace("F\uf769\uf767.", "Fig.")


def normalize_page(stem, page, md):
    if stem.startswith("shamir"):
        md = re.sub(r"(?m)^(?:#{1,6}\s+|-\s+)?(?:\d+ • A\. Shamir|Constraint-Based Approach for Automatic Hinting of Digital Typefaces • \d+)\s*$", "", md)
        md = re.sub(r"ACM Transactions on Graphics, Vol\. 22, No\. 2, April 2003(?:, Pages 131–151)?\.", "", md)
        md = re.sub(r"(?m)^(?:-\s+)?(\d+\.\d+)\s+([A-Z][^\n]+)$", r"### \1 \2", md)
        md = re.sub(r"(?m)^(?:-\s+)?([1-6])\.\s+([A-Z][A-Z ]+)$", r"## \1. \2", md)
    if stem.startswith("hersch"):
        md = re.sub(r"(?m)^- ((?:1|10|11|12) (?:Introduction|Remaining problems|Conclusions|Acknowlegments))$", r"## \1", md)
    return md


def finalize_page(stem, page, md):
    if stem.startswith("turner"):
        md = re.sub(r"```\n(.*?)\n```", r"```c\n\1\n```", md, flags=re.S)
    return md
