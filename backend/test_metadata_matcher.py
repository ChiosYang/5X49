import unittest

from app.services.metadata.matcher import generate_search_queries, parse_title_year, score_candidates


class MetadataMatcherTests(unittest.TestCase):
    def test_parse_removes_common_release_terms(self):
        title, year = parse_title_year("The.Matrix.1999.2160p.UHD.BluRay.x265-GROUP.mkv")

        self.assertEqual(title, "The Matrix")
        self.assertEqual(year, 1999)

    def test_parse_removes_edition_terms_before_year(self):
        title, year = parse_title_year("Movie.Name.Extended.Cut.2001.REMUX.mkv")

        self.assertEqual(title, "Movie Name")
        self.assertEqual(year, 2001)

    def test_parse_keeps_hyphenated_title_words(self):
        title, year = parse_title_year("Spider-Man.2002.1080p.BluRay.mkv")

        self.assertEqual(title, "Spider Man")
        self.assertEqual(year, 2002)

    def test_generate_search_queries_splits_mixed_language_titles(self):
        title, year = parse_title_year("卧虎藏龙.Crouching.Tiger.Hidden.Dragon.2000.mkv")
        queries = generate_search_queries(title)

        self.assertEqual(year, 2000)
        self.assertIn("卧虎藏龙 Crouching Tiger Hidden Dragon", queries)
        self.assertIn("Crouching Tiger Hidden Dragon", queries)
        self.assertIn("卧虎藏龙", queries)

    def test_score_prefers_exact_title_and_year(self):
        results = [
            {
                "id": 603,
                "title": "The Matrix",
                "original_title": "The Matrix",
                "release_date": "1999-03-31",
                "popularity": 20,
            },
            {
                "id": 604,
                "title": "The Matrix Reloaded",
                "original_title": "The Matrix Reloaded",
                "release_date": "2003-05-15",
                "popularity": 200,
            },
        ]

        candidates = score_candidates("The Matrix", 1999, results)

        self.assertEqual(candidates[0].tmdb_id, 603)
        self.assertGreaterEqual(candidates[0].score, 90)
        self.assertLess(candidates[1].score, candidates[0].score)

    def test_missing_year_does_not_auto_confidently_match(self):
        results = [
            {
                "id": 603,
                "title": "The Matrix",
                "original_title": "The Matrix",
                "release_date": "1999-03-31",
                "popularity": 20,
            }
        ]

        candidates = score_candidates("The Matrix", 0, results)

        self.assertLess(candidates[0].score, 80)


if __name__ == "__main__":
    unittest.main()
