"""Regression tests for V14 grouping, threshold, and category coverage."""
import importlib.util
import unittest
from pathlib import Path
from datetime import datetime, timezone
spec=importlib.util.spec_from_file_location("scan",Path(__file__).with_name("scan.py"))
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class TestCloudHunter(unittest.TestCase):
    def test_21_distinct_ids(self):
        rows=[{"ad_id":str(i),"product_name":"Hair growth strengthening serum premium","landing_url":"https://store.example/products/hair-growth-serum-strengthening"} for i in range(21)]
        keys=[m.product_identity(x)[0] for x in rows]
        self.assertTrue(all(k==keys[0] for k in keys))
        self.assertEqual(len(set(a["ad_id"] for a in rows)),21)
        self.assertEqual(m.MIN_ACTIVE_ADS,21)
        self.assertNotEqual(m.product_identity({"ad_id":"99","product_name":"Shampoo", "landing_url":"https://store.example/products/hair-growth-serum-strengthening"})[0],m.product_identity({"ad_id":"99","product_name":"Shampoo", "landing_url":"https://store.example/products/other-skin-care-cream"})[0])
    def test_categories_and_country_exclusion(self):
        self.assertEqual(m.classify_name("hair serum"),"beauty")
        self.assertEqual(m.classify_name("wireless charger"),"electronics")
        self.assertFalse(set(m.COUNTRIES)&m.EXCLUDED_COUNTRIES)
    def test_status_is_not_completion(self):
        self.assertEqual(m.TARGET_PER_CATEGORY,50)
        self.assertEqual(m.MAX_QUERIES_PER_RUN,12)
        self.assertEqual(m.MAX_RESULTS_PER_QUERY,180)

if __name__=="__main__": unittest.main()
