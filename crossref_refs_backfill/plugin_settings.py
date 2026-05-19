"""
Janeway plugin: Crossref reference-list backfill.

Hooks into Janeway's existing Crossref deposit pipeline to contribute
`<citation_list>` data for articles whose render galley isn't JATS XML.
Closes the gap that leaves journals like Poroi depositing empty
`<citation_list/>` elements in Crossref despite having parseable
references in their HTML/PDF galleys.

The plugin contributes three citation-list providers (cached, HTML
galley, PDF galley) registered with the deposit pipeline in priority
order. The provider-registration mechanism here matches the proposal in
INTEGRATION-SKETCH.md; if Andy lands a different shape after the call
this `install()` is the only function that changes.
"""

from utils import plugins


PLUGIN_NAME = "Crossref Reference Backfill"
DISPLAY_NAME = "crossref_refs_backfill"
DESCRIPTION = (
    "Contributes citation_list XML to Crossref deposits for articles "
    "whose render galley isn't JATS XML. Parses references directly "
    "from HTML galleys when available, falls back to GROBID on PDFs."
)
AUTHOR = "Justin Lewis"
VERSION = "0.1.0"
JANEWAY_VERSION = "1.7.0"
SHORT_NAME = "crossref_refs_backfill"
MANAGER_URL = "crossref_refs_backfill_manager"
JANEWAY_PLUGIN = True


class CrossrefRefsBackfillPlugin(plugins.Plugin):
    plugin_name = PLUGIN_NAME
    display_name = DISPLAY_NAME
    description = DESCRIPTION
    author = AUTHOR
    short_name = SHORT_NAME

    manager_url = MANAGER_URL

    version = VERSION
    janeway_version = JANEWAY_VERSION


def install():
    """Register the plugin and its citation providers.

    The provider-registration call here depends on a small core change
    proposed in INTEGRATION-SKETCH.md — a module-level list in
    `identifiers/logic.py` that `extract_citations_for_crossref` falls
    through to when its current JATS-galley path returns None.

    If Andy prefers a different mechanism (signal, Django settings list,
    plugin registry class), this is the only function in the plugin
    that has to change. The providers themselves don't care how they
    get called.
    """
    CrossrefRefsBackfillPlugin.install()

    # Provider registration — exact shape pending Andy's review.
    try:
        from identifiers.logic import register_citation_provider
    except ImportError:
        # Core PR not yet landed. The plugin still installs but won't
        # contribute citations to deposits until the registration hook
        # exists upstream.
        return

    from crossref_refs_backfill.providers import (
        from_stored_reference_list,
        from_html_galley,
        from_pdf_galley,
    )

    # Order matters: cached results first (cheapest), then HTML parse
    # (high confidence, no external deps), then GROBID/PDF (slowest,
    # requires the GROBID sidecar to be reachable).
    register_citation_provider(from_stored_reference_list)
    register_citation_provider(from_html_galley)
    register_citation_provider(from_pdf_galley)


def hook_registry():
    """Janeway template hooks. Empty in this iteration."""
    return {}
