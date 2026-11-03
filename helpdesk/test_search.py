"""Knowledge Base article indexing in RediSearch (helpdesk.search).

Needs a Redis cache with the RediSearch module (redis-stack); the tests skip otherwise.
"""

import unittest
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from redis.exceptions import ResponseError

from helpdesk import search as hd_search
from helpdesk.search import HelpdeskSearch, search, update_article_index
from helpdesk.test_utils import make_article


def has_redisearch() -> bool:
    try:
        frappe.cache().ft("helpdesk_probe_idx").info()
    except ResponseError as e:
        return "unknown" in str(e).lower()  # the command exists, the index just does not
    except Exception:
        return False
    return True


def indexed_names(article: str) -> list[str]:
    """Names of the indexed sections of `article`."""
    return sorted(
        k.decode().split("HD Article:", 1)[1]
        for k in frappe.cache().get_keys(f"search_doc:HD Article:{article}#")
    )


@unittest.skipUnless(has_redisearch(), "RediSearch is not available")
class TestArticleIndexing(FrappeTestCase):
    def setUp(self):
        HelpdeskSearch().drop_index()
        HelpdeskSearch().build_index()
        self.addCleanup(HelpdeskSearch().drop_index)

    def test_draft_is_never_indexed(self):
        article = make_article("Draft Article", status="Draft")
        update_article_index(article)
        self.assertEqual(indexed_names(article), [])

    def test_publish_edit_unpublish_and_delete(self):
        article = make_article("Lifecycle Article", content="<h2>Setup</h2><p>first body</p>")
        update_article_index(article)
        self.assertTrue(indexed_names(article))

        frappe.db.set_value("HD Article", article, "content", "<h2>Other</h2><p>second body</p>")
        update_article_index(article)
        names = indexed_names(article)
        self.assertTrue(any(n.endswith("#other") for n in names))
        self.assertFalse(any(n.endswith("#setup") for n in names))

        frappe.db.set_value("HD Article", article, "status", "Draft")
        update_article_index(article)
        self.assertEqual(indexed_names(article), [])

        frappe.db.set_value("HD Article", article, "status", "Published")
        update_article_index(article)
        frappe.delete_doc("HD Article", article, force=True)
        update_article_index(article)
        self.assertEqual(indexed_names(article), [])

    def test_repeated_indexing_makes_no_duplicates(self):
        article = make_article("Repeat Article")
        update_article_index(article)
        first = indexed_names(article)
        for _ in range(3):
            update_article_index(article)
        self.assertEqual(indexed_names(article), first)
        self.assertEqual(HelpdeskSearch().redis.ft(HelpdeskSearch().index_name).info()["num_docs"], str(len(first)))

    def test_missing_index_is_rebuilt_in_full(self):
        one, two = make_article("First Article"), make_article("Second Article")
        HelpdeskSearch().drop_index()
        update_article_index(one)
        self.assertTrue(indexed_names(one))
        self.assertTrue(indexed_names(two))

    def test_search_returns_published_articles_and_empty_for_no_match(self):
        make_article("Zebra Article", content="<p>zebraunique content</p>")
        HelpdeskSearch().build_index()
        found = search("zebraunique")
        self.assertTrue(found and found[0]["items"])
        self.assertEqual(search("qqqnomatchqqq"), [])

    def test_search_without_an_index_returns_an_empty_list(self):
        HelpdeskSearch().drop_index()
        self.assertEqual(search("anything"), [])

    def test_search_survives_redis_errors(self):
        with patch.object(hd_search.HelpdeskSearch, "search", side_effect=ResponseError("boom")):
            self.assertEqual(search("anything"), [])
