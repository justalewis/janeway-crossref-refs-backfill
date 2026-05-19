"""
Janeway plugin: Crossref reference-list backfill.

Hooks into Janeway's existing Crossref deposit pipeline to contribute
`<citation_list>` data for articles whose render galley isn't JATS XML.
Closes the gap that leaves journals like Poroi depositing empty
`<citation_list/>` elements in Crossref despite having parseable
references in their HTML/PDF galleys.

Structure follows the conventions used by openlibhums/datacite — same
shape of plugin class, install hook, settings-from-JSON, event
registration. The architectural decision still pending Andy's review
is how citation providers should be registered (see
INTEGRATION-SKETCH.md).
"""

from django.conf import settings

from utils import plugins
from utils.install import update_settings


PLUGIN_NAME = "Crossref Reference Backfill"
DISPLAY_NAME = "Crossref Refs Backfill"
DESCRIPTION = (
    "Contributes citation_list XML to Crossref deposits for articles "
    "whose render galley isn't JATS XML. Parses references directly "
    "from HTML galleys when available, falls back to GROBID on PDFs."
)
AUTHOR = "Justin Lewis"
VERSION = "0.1"
SHORT_NAME = "crossref_refs_backfill"
MANAGER_URL = "crossref_refs_backfill_manager"
JANEWAY_VERSION = "1.7.0"

# GROBID sidecar endpoint. Used by the Tier 3 provider; the plugin
# silently skips Tier 3 if GROBID isn't reachable, so a missing or
# wrong value here doesn't break Tier 1/2 deposits.
GROBID_URL = "http://localhost:8070"

if settings.DEBUG:
    # Match datacite's pattern of swapping to a test endpoint in DEBUG.
    # GROBID itself doesn't have a test server, so this is the same URL
    # — left as a hook in case we add a dev sidecar later.
    GROBID_URL = "http://localhost:8070"


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
    """Register the plugin and load its per-journal settings."""
    CrossrefRefsBackfillPlugin.install()
    update_settings(
        file_path="plugins/crossref_refs_backfill/install/settings.json",
    )


def hook_registry():
    """Janeway template hooks. Empty in this iteration; could add a
    backfill-status item to the manager nav once UI is real."""
    return CrossrefRefsBackfillPlugin.hook_registry()


def register_for_events():
    """Register citation-provider callbacks.

    OPEN ARCHITECTURAL QUESTION (see INTEGRATION-SKETCH.md). Two
    candidate mechanisms:

    1. New event in core (preferred-looking after surveying existing
       plugins): an `ON_CROSSREF_CITATION_LIST_BUILD` event fired by
       `extract_citations_for_crossref` when the JATS-galley path
       returns None. Plugins register callbacks here. Question for
       Andy: does Janeway's event system support collecting return
       values from callbacks (we need the first non-None XML string,
       not fire-and-forget)?

    2. New module-level list in `identifiers/logic.py` with a
       `register_citation_provider` function. Less idiomatic but
       clearer about return-value semantics.

    Until Andy weighs in, this function is a no-op. The providers
    themselves live in `providers.py` and are mechanism-agnostic.
    """
    return
