"""
Backfill the citation-list cache for a journal's catalog.

Walks the published articles of a journal, calls the same providers
the deposit pipeline uses, and stores the extracted <citation_list>
XML in ParsedReferenceList. Subsequent Crossref deposits read from
the cache and never re-parse galleys.

usage:
    python manage.py backfill_references --journal poroi --dry-run
    python manage.py backfill_references --journal poroi --batch-size 25 --resume

This is a one-time-per-journal operation. For ongoing-mode behavior
(extract on publish), subscribe `from_html_galley` / `from_pdf_galley`
to `ON_ARTICLE_PUBLISHED` — pending Andy's input on whether that's a
plugin concern or a core concern.
"""

from __future__ import annotations

import time

from django.core.management.base import BaseCommand, CommandError

from crossref_refs_backfill.models import ParsedReferenceList
from crossref_refs_backfill.providers import (
    from_html_galley,
    from_pdf_galley,
)


class Command(BaseCommand):
    help = "Backfill citation_list XML for every published article in a journal."

    def add_arguments(self, parser):
        parser.add_argument(
            "--journal",
            required=True,
            help="Journal code (e.g. 'poroi').",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Extract and report, but don't write to ParsedReferenceList.",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=25,
            help="Articles per batch. Pause briefly between batches.",
        )
        parser.add_argument(
            "--resume",
            action="store_true",
            help="Skip articles that already have a ParsedReferenceList entry.",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Re-extract even when a ParsedReferenceList entry exists.",
        )

    def handle(self, *args, **options):
        from journal.models import Journal
        from submission.models import Article

        try:
            journal = Journal.objects.get(code=options["journal"])
        except Journal.DoesNotExist as e:
            raise CommandError(f"Journal '{options['journal']}' not found") from e

        # Published articles only. The deposit pipeline only operates on
        # articles with a registered DOI, but extracting earlier doesn't
        # hurt — references stay cached until needed.
        articles = Article.objects.filter(
            journal=journal,
            stage="Published",
        ).order_by("id")

        if options["resume"] and not options["force"]:
            already_cached = ParsedReferenceList.objects.filter(
                article__journal=journal,
            ).values_list("article_id", flat=True)
            articles = articles.exclude(id__in=list(already_cached))

        total = articles.count()
        self.stdout.write(
            f"Backfilling {total} article(s) from journal '{journal.code}' "
            f"(dry-run={options['dry_run']})"
        )

        counts = {"tier1": 0, "tier2": 0, "tier3": 0, "skipped": 0, "failed": 0}
        for i, article in enumerate(articles.iterator(chunk_size=options["batch_size"]), 1):
            try:
                citation_list_xml = (
                    from_html_galley(article)
                    or from_pdf_galley(article)
                )
            except Exception as e:
                self.stderr.write(f"  !! article {article.pk}: {e}")
                counts["failed"] += 1
                continue

            if not citation_list_xml:
                counts["skipped"] += 1
                self.stdout.write(f"  [{i}/{total}] article {article.pk}: no references extracted")
                continue

            # Providers cache automatically on success. In --dry-run we
            # want to undo that side effect.
            if options["dry_run"]:
                ParsedReferenceList.objects.filter(article=article).delete()

            try:
                cached = article.parsed_reference_list
                counts[cached.tier] = counts.get(cached.tier, 0) + 1
                self.stdout.write(
                    f"  [{i}/{total}] article {article.pk}: "
                    f"{cached.references_count} refs ({cached.tier})"
                )
            except ParsedReferenceList.DoesNotExist:
                counts["skipped"] += 1

            # Polite pause between batches so we're nice to GROBID and
            # to whatever's running alongside the Janeway worker.
            if i % options["batch_size"] == 0:
                time.sleep(1.0)

        self.stdout.write("")
        self.stdout.write(
            f"Done. tier1={counts['tier1']}, tier2={counts['tier2']}, "
            f"tier3={counts['tier3']}, skipped={counts['skipped']}, "
            f"failed={counts['failed']}"
        )
