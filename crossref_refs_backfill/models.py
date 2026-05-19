"""
Plugin-owned models. One model: ParsedReferenceList caches per-article
extraction results so we don't re-parse galleys on every Crossref
deposit attempt.

Owned entirely by this plugin — no changes to core models. If Andy
wants references stored in a core model (so other plugins can read
them too), that's a separate PR; the cache here would migrate or be
removed at that point.
"""

from django.db import models


TIER_CHOICES = [
    ("tier1", "Structured HTML (<p class='ref'>)"),
    ("tier2", "Footnoted HTML (Chicago notes-bibliography)"),
    ("tier3", "PDF + GROBID"),
]


class ParsedReferenceList(models.Model):
    """Per-article cache of extracted citation_list XML.

    The citation_list_xml field holds the bare <citation_list>...</citation_list>
    fragment exactly as it would appear in a Crossref deposit. The
    deposit pipeline reads it verbatim via `from_stored_reference_list`.
    """

    article = models.OneToOneField(
        "submission.Article",
        on_delete=models.CASCADE,
        related_name="parsed_reference_list",
    )
    citation_list_xml = models.TextField(
        help_text=(
            "Crossref <citation_list> XML extracted from the article's "
            "galley. Used as-is in Crossref deposits when the article's "
            "render galley isn't JATS XML."
        ),
    )
    tier = models.CharField(
        max_length=10,
        choices=TIER_CHOICES,
        help_text="Which extractor produced this result.",
    )
    references_count = models.PositiveIntegerField(default=0)
    matched_doi_count = models.PositiveIntegerField(
        default=0,
        help_text="Number of references whose <doi> was confirmed via Crossref matching.",
    )
    extracted_at = models.DateTimeField(auto_now=True)
    requires_review = models.BooleanField(
        default=False,
        help_text=(
            "Set when extraction confidence is below threshold (Tier 2 mixed-content "
            "footnotes, Tier 3 PDFs with low GROBID confidence). The journal manager "
            "should spot-check before allowing deposit."
        ),
    )

    class Meta:
        verbose_name = "Parsed reference list"
        verbose_name_plural = "Parsed reference lists"

    def __str__(self):
        return f"[{self.tier}] {self.article} — {self.references_count} refs"
