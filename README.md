# crossref_refs_backfill

A Janeway plugin that contributes Crossref `<citation_list>` data for articles whose render galley isn't JATS XML.

Closes the gap that leaves journals like *Poroi* depositing empty `<citation_list/>` elements in Crossref despite having structured references in their HTML galleys (or recoverable references in their PDF galleys).

**Status:** Scaffold / pre-design-review. Structure follows the conventions used by [`openlibhums/datacite`](https://github.com/openlibhums/datacite) (also a metadata-deposit plugin, and a useful template since Andy Byers wrote it). Functional plugin code, but depends on a small upstream change in `openlibhums/janeway` (proposed in [INTEGRATION-SKETCH.md](./INTEGRATION-SKETCH.md)) to register citation providers with the existing deposit pipeline. The current `install()` falls back gracefully if the upstream hook isn't present.

## What it does

When a Crossref deposit is being built for an article that lacks a JATS XML render galley, the plugin's three providers are tried in order:

1. **`from_stored_reference_list`** — return cached citation_list XML from a prior extraction (fastest)
2. **`from_html_galley`** — parse references from an HTML galley using Tier 1 (`<p class="ref">`) or Tier 2 (footnoted Chicago notes) detection
3. **`from_pdf_galley`** — POST a PDF galley to GROBID, parse the TEI output (slowest; skipped silently if GROBID isn't reachable)

First non-None result wins. Results are cached in `ParsedReferenceList` so subsequent deposits don't re-parse.

## Empirical baseline

From an 8-galley Poroi sample (May 2026), 203 total references, 87 matched a Crossref DOI after enrichment:

| Tier | Source type | Match rate |
|---|---|---|
| Tier 1 | structured HTML | ~30–38% |
| Tier 2 | footnoted HTML  | ~22% |
| Tier 3 | PDF + GROBID    | 17–57% (Janeway-era at the high end) |

Match rates put *Poroi* in the same band as *Across the Disciplines* and *The WAC Journal* (other Justin-Lewis journal scrapers), with the Janeway-era pool tracking the WAC Journal's recent-volumes band.

## Repository layout

```
crossref_refs_backfill/
├─ plugin_settings.py            Janeway plugin metadata + install/hook/events
├─ install/
│  └─ settings.json              per-journal settings (enable, GROBID URL)
├─ models.py                     ParsedReferenceList cache
├─ providers.py                  three providers wired to the extractors
├─ urls.py                       manager + article-list + article-detail routes
├─ views.py                      manager UI (scaffold-level)
├─ templates/crossref_refs_backfill/
│  └─ manager.html               per-journal backfill status
├─ extractors/
│  ├─ detect.py                  tier detection
│  ├─ tier1.py                   structured-HTML parser
│  ├─ tier2.py                   footnoted-HTML parser
│  ├─ tier3.py                   PDF + GROBID parser
│  └─ build_xml.py               <citation_list> emitter
├─ management/
│  └─ commands/
│     └─ backfill_references.py  one-time-per-journal backfill orchestrator
├─ migrations/                   (run makemigrations after install)
└─ tests/                        (placeholder; tests against Poroi samples to come)
```

When installed in a Janeway instance, this plugin lives at `janeway/src/plugins/crossref_refs_backfill/` and imports use the `plugins.crossref_refs_backfill.X` namespace.

## How this relates to the Poroi sandbox

The standalone scraper at `C:\Users\Justin\Desktop\Journal Reference Scrapers\Poroi\` is the development sandbox where the three extractors and the CrossRef-matching enricher were validated. The code in `extractors/` is a port from there with one adaptation: each tier's primary entry point takes content (bytes or text) directly so the plugin can pass `galley.file.get_file(article)` without writing to disk.

The sandbox stays in place after this plugin lands. It's the right environment for adding new tiers (e.g., for journals on other platforms), tightening the heuristics, or running before-and-after comparisons.

## Open architectural questions

Pending Andy Byers's review at the call. See `INTEGRATION-SKETCH.md` for the full list. The biggest one:

- **Provider-registration mechanism.** Janeway has an existing event system (`events_logic.Events.register_for_event(EVENT, callback)`) which other plugins use to subscribe to lifecycle hooks like `ON_ARTICLE_ACCEPTED`. The cleanest version of our change might be a new `ON_CROSSREF_CITATION_LIST_BUILD` event that fires when `extract_citations_for_crossref` would otherwise return None — provided the event system can collect callback return values (a question for Andy). Alternative: a new module-level list with a `register_citation_provider` function. The providers themselves don't care which mechanism; only `register_for_events()` (or equivalent) would change.

## License

AGPL v3 (to match Janeway's license).
