from django.urls import re_path

from plugins.crossref_refs_backfill import views


urlpatterns = [
    re_path(
        r"^manager/$",
        views.manager,
        name="crossref_refs_backfill_manager",
    ),
    re_path(
        r"^articles/$",
        views.article_list,
        name="crossref_refs_backfill_articles",
    ),
    re_path(
        r"^articles/(?P<article_id>\d+)/$",
        views.article_detail,
        name="crossref_refs_backfill_article_detail",
    ),
]
