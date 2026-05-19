"""
Manager UI views. Stub-level for the scaffold — enough that the URLs
resolve and templates render, not yet enough for a production manager
experience.

Real fleshing-out happens after the design call with Andy: the
manager page should show per-tier counts, the article list should
expose `requires_review` filter, and the article detail page should
let a journal admin spot-check parsed references before they go to
Crossref.
"""

from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render

from plugins.crossref_refs_backfill.models import ParsedReferenceList
from security.decorators import editor_user_required
from submission import models as submission_models


@login_required
@editor_user_required
def manager(request):
    """Plugin manager page. Per-journal summary of backfill status."""
    cached = ParsedReferenceList.objects.filter(
        article__journal=request.journal,
    )
    by_tier = {tier: cached.filter(tier=tier).count() for tier in ("tier1", "tier2", "tier3")}
    context = {
        "plugin_name": "Crossref Reference Backfill",
        "cached_total": cached.count(),
        "by_tier": by_tier,
        "review_pending": cached.filter(requires_review=True).count(),
    }
    return render(request, "crossref_refs_backfill/manager.html", context)


@login_required
@editor_user_required
def article_list(request):
    """List articles in this journal with their cached reference data."""
    cached = ParsedReferenceList.objects.filter(
        article__journal=request.journal,
    ).select_related("article").order_by("-extracted_at")
    return render(request, "crossref_refs_backfill/article_list.html", {
        "cached": cached,
    })


@login_required
@editor_user_required
def article_detail(request, article_id):
    """Per-article detail showing parsed references for spot-checking."""
    article = get_object_or_404(
        submission_models.Article,
        pk=article_id,
        journal=request.journal,
    )
    cached = ParsedReferenceList.objects.filter(article=article).first()
    return render(request, "crossref_refs_backfill/article_detail.html", {
        "article": article,
        "cached": cached,
    })
