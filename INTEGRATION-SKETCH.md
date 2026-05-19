# Janeway integration sketch — pre-call notes

A working sketch for the Janeway-side integration of the Poroi reference scraper. Ready to walk Andy through on the call. Not a final design — the goal is to give us a concrete artifact to react to so the call surfaces decisions rather than open-ended discussion.

## Where the deposit flow currently lives

The Crossref deposit pipeline is concentrated in `src/identifiers/logic.py`. The orchestration chain:

```
register_batch_of_crossref_dois(articles)
  └── send_crossref_deposit(test_mode, identifiers, journal)
        └── render_to_string("common/identifiers/crossref_doi_batch.xml", context)
              └── (per article) create_crossref_article_context(article, identifier)
                    └── extract_citations_for_crossref(article)   ← THE INTEGRATION POINT
```

Per-article XML rendering happens via the Django template in `src/templates/common/identifiers/crossref_article.xml`, which contains:

```django
{% if article.scheduled and article.citation_list %}
    {{ article.citation_list|safe }}
{% else %}
    <citation_list/>
{% endif %}
```

Two consequences:

- The deposit pipeline expects `article.citation_list` (the value computed by `extract_citations_for_crossref`) to be a string of well-formed Crossref `<citation_list>...</citation_list>` XML, or `None`/falsy.
- Our scraper's `04_build_crossref_xml.py` already produces exactly this shape, so there's no format conversion needed — only a delivery question.

## The integration point in detail

`extract_citations_for_crossref(article)` at `src/identifiers/logic.py:441`:

```python
def extract_citations_for_crossref(article):
    """Extracts the citations in a format compatible for crossref deposits

    It can only handle articles with an XML galley using a DTD
    compatible with the XSL provided by crossref themselves
    """
    render_galley = article.get_render_galley
    citations = None
    if render_galley and render_galley.type == "xml":
        try:
            xml_transformed = render_galley.render_crossref()
            souped_xml = BeautifulSoup(str(xml_transformed), "lxml")
            citation_list = souped_xml.find("citation_list")
            # ... DOI normalization + cYear casing fix ...
            if citation_list:
                citations = str(citation_list.extract())
        except Exception as e:
            logger.info("Error transforming Crossref citations: %s" % e)
    else:
        logger.debug("No XML galleys found for crossref citation extraction")
    return citations
```

Articles whose render galley is HTML or PDF — most of Poroi — fall through the `else` branch and contribute `<citation_list/>` (empty) to the deposit.

## Proposed change

A small extension to `extract_citations_for_crossref` that lets installed plugins contribute citation_list XML when the existing JATS-XML path returns nothing. Existing behavior is fully preserved.

```python
# src/identifiers/logic.py

_CITATION_PROVIDERS: list[Callable[[Article], str | None]] = []


def register_citation_provider(provider):
    """Register a callable that returns a Crossref <citation_list> XML
    string for the given article, or None if it has nothing to contribute.

    Providers are tried in registration order; the first non-None result
    is used. Plugins call this from their plugin_settings.install().
    """
    _CITATION_PROVIDERS.append(provider)


def extract_citations_for_crossref(article):
    # 1. Existing JATS-galley path. Unchanged.
    render_galley = article.get_render_galley
    if render_galley and render_galley.type == "xml":
        # ... (existing body) ...
        if citations:
            return citations

    # 2. NEW: try registered providers in order.
    for provider in _CITATION_PROVIDERS:
        try:
            citations = provider(article)
            if citations:
                return citations
        except Exception as e:
            logger.warning(
                "Citation provider %s failed for article %s: %s",
                provider.__name__, article.pk, e,
            )

    return None
```

Total core diff: ~15 lines, no schema changes, no migrations. Existing journals that already deposit references via JATS galleys see no behavior change.

### Alternative shape: use the existing event system

After surveying existing Janeway plugins (`openlibhums/datacite`, `openlibhums/back_content`, etc.), the conventional mechanism for plugins to hook into deposit-pipeline lifecycle is the `events_logic.Events.register_for_event(EVENT, callback)` registry. Datacite uses it to subscribe `register_doi_automatically` to `ON_ARTICLE_ACCEPTED`, etc.

A version of the change that uses this idiom instead of a new registry list:

```python
# src/identifiers/logic.py

from events import logic as events_logic

# Register a new event name. Convention: ON_<DOMAIN>_<VERB>.
events_logic.Events.ON_CROSSREF_CITATION_LIST_BUILD = "on_crossref_citation_list_build"


def extract_citations_for_crossref(article):
    # Existing JATS-galley path. Unchanged.
    # ...
    if citations:
        return citations

    # NEW: fire the event; first callback to return a string wins.
    results = events_logic.Events.raise_event(
        events_logic.Events.ON_CROSSREF_CITATION_LIST_BUILD,
        article=article,
    )
    for result in (results or []):
        if result:
            return result

    return None
```

Open question for Andy: **does `Events.raise_event` return callback values, or is it fire-and-forget?** If fire-and-forget, the registry-list option above is cleaner; if it returns values, the event-based version is more idiomatic. This is the load-bearing thing to settle in the call.

## What the plugin contributes

The plugin (separate repo, AGPLv3, follows `BirkbeckCTP/generic_plugin_generator` layout) registers three providers in priority order:

```python
# crossref_refs_backfill/plugin_settings.py

def install():
    from identifiers.logic import register_citation_provider
    from crossref_refs_backfill.providers import (
        from_stored_reference_list,   # cache: parsed result stored on the plugin model
        from_html_galley,             # Tier 1 / Tier 2: parse on-demand from HTML galley
        from_pdf_galley,              # Tier 3: GROBID parse on-demand from PDF galley
    )
    register_citation_provider(from_stored_reference_list)
    register_citation_provider(from_html_galley)
    register_citation_provider(from_pdf_galley)
```

The three providers, sketched:

```python
# crossref_refs_backfill/providers.py

def from_stored_reference_list(article):
    """Cached path. Returns citation_list XML if a previous extraction
    stored one for this article."""
    stored = ParsedReferenceList.objects.filter(article=article).first()
    return stored.citation_list_xml if stored else None


def from_html_galley(article):
    """Tier 1 / Tier 2. Parse references from an HTML galley on-demand
    if one exists. Caches the result via ParsedReferenceList."""
    html_galley = article.galley_set.filter(
        file__mime_type="text/html",
    ).order_by("sequence").first()
    if not html_galley:
        return None
    html = html_galley.file.get_file(article)
    refs = _extract_from_html(html)   # tier1/tier2 dispatch
    if not refs:
        return None
    citation_list_xml = _to_citation_list_xml(refs)
    ParsedReferenceList.objects.update_or_create(
        article=article,
        defaults={"citation_list_xml": citation_list_xml, "tier": _detected_tier},
    )
    return citation_list_xml


def from_pdf_galley(article):
    """Tier 3. POST a PDF galley to GROBID, parse the TEI output, and
    cache the result. Skipped when GROBID is not configured for this
    instance."""
    pdf = article.pdfs.order_by("sequence").first()
    if not pdf or not GROBID_URL:
        return None
    refs = _extract_via_grobid(pdf.file.get_file(article))
    if not refs:
        return None
    citation_list_xml = _to_citation_list_xml(refs)
    ParsedReferenceList.objects.update_or_create(
        article=article,
        defaults={"citation_list_xml": citation_list_xml, "tier": "tier3"},
    )
    return citation_list_xml
```

The `_extract_from_html` and `_extract_via_grobid` functions are the same code currently in `Poroi/scripts/02_*` — ported into the plugin as `crossref_refs_backfill/extractors/`.

## Plugin model

One small model, owned by the plugin:

```python
# crossref_refs_backfill/models.py

class ParsedReferenceList(models.Model):
    article = models.OneToOneField(
        "submission.Article",
        on_delete=models.CASCADE,
        related_name="parsed_reference_list",
    )
    citation_list_xml = models.TextField(
        help_text="Crossref <citation_list> XML extracted from the article's galley.",
    )
    tier = models.CharField(
        max_length=10,
        choices=[("tier1", "Structured HTML"),
                 ("tier2", "Footnoted HTML"),
                 ("tier3", "PDF + GROBID")],
    )
    extracted_at = models.DateTimeField(auto_now=True)
    requires_review = models.BooleanField(
        default=False,
        help_text="Set when extraction confidence is below threshold "
                  "(typical for tier2 mixed-content footnotes and tier3 PDFs).",
    )
```

This is the only schema addition. Stays in plugin space; never touches core models.

## Backfill orchestration

A management command in the plugin walks a journal's catalog and pre-populates `ParsedReferenceList` entries:

```bash
python manage.py backfill_references --journal poroi --dry-run
python manage.py backfill_references --journal poroi --batch-size 25 --resume
```

The command is independent of deposit timing. It's a one-time-per-journal extraction pass; afterward, every Crossref deposit picks up the cached references via `from_stored_reference_list` automatically.

## Plugin layout

```
crossref_refs_backfill/
├─ plugin_settings.py            name, version, install()
├─ models.py                     ParsedReferenceList
├─ providers.py                  the three providers above
├─ extractors/
│  ├─ tier1.py                   ← from Poroi/scripts/02_extract_tier1.py
│  ├─ tier2.py                   ← from Poroi/scripts/02b_extract_tier2.py
│  ├─ tier3.py                   ← from Poroi/scripts/02c_extract_tier3.py
│  └─ build_xml.py               ← from Poroi/scripts/04_build_crossref_xml.py
├─ management/commands/
│  └─ backfill_references.py     orchestrator
└─ tests/
   └─ ...
```

The standalone scraper at `C:\Users\Justin\Desktop\Journal Reference Scrapers\Poroi\` becomes the pre-Janeway development sandbox: same code, validated against real samples, then ported into the plugin once the integration shape is settled.

## Open questions for the call

The places where Andy's input shapes the architecture before code is written:

1. **The provider-registration shape.** Is a module-level list with `register_citation_provider()` the right idiom for Janeway plugins, or do you have a preferred mechanism — Django settings list, signal/event, a dedicated registry class? The first matters because plugins should hook in without monkey-patching, but Janeway has its own conventions and I don't want to invent a new one if there's already a precedent.

2. **Caching location.** The plugin owns a `ParsedReferenceList` model right now. Reasonable, or would you rather a caching layer in core that any provider plugin can populate? The latter would let multiple plugins share a cache and would survive plugin uninstalls.

3. **Provider order.** Currently registration order = priority. Could be made explicit with a `priority=N` keyword. Worth it, or YAGNI?

4. **Failure handling.** A provider that raises is currently logged and skipped (the next provider tries). Is that the right policy, or do you want hard-fail-on-error for diagnostic reasons?

5. **Backfill discoverability.** Should the backfill management command live in the plugin or in core? If core, multiple journals can use it; if plugin, it stays scoped to the citation-list use case.

6. **Test mode interaction.** `send_crossref_deposit` has a `test_mode` flag that points at Crossref's test server. Should plugin-contributed citation lists be subject to any extra validation in test mode (e.g. schema-validate the XML before attempting deposit)?

7. **The reference-data lifecycle going forward.** For journals like Poroi where new articles arrive as PDF-only, the backfill command can be re-run periodically — but there's also an `ON_ARTICLE_PUBLISHED` event we could hook to extract eagerly. Do you want the plugin to subscribe to that, or stay strictly pull-based?

## Pre-call agenda (rough, 30 min)

1. **5 min.** Walk through the integration point — open `logic.py:441` and `crossref_article.xml:91`, agree on what changes.
2. **10 min.** Provider-chain shape (Q1, Q3, Q4) — pick the registration mechanism. This is the load-bearing decision.
3. **5 min.** Plugin model and caching (Q2) — agree on whether `ParsedReferenceList` lives in plugin or core.
4. **5 min.** Backfill command location (Q5) and event-subscription (Q7) — quick decisions.
5. **5 min.** Open road — anything Andy wants to surface that isn't on this list.

Followups (post-call): I open a draft GitHub issue capturing the agreed shape and a small WIP PR for the core change so we can both react to real code rather than abstract architecture.
