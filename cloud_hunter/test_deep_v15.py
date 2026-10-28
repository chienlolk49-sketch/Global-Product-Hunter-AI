import unittest
from datetime import datetime, timezone
from cloud_hunter import deep_v15 as d

NOW=datetime(2026,10,28,8,0,tzinfo=timezone.utc)

def ad(i,slug="standing-makeup-bag-portable-large-capacity",host="doresty.store",status=True):
    return {"ad_id":str(i),"product_name":slug.replace("-"," "),
            "ad_url":"https://www.facebook.com/ads/library/?id="+str(i),
            "landing_url":f"https://{host}/products/{slug}",
            "source_countries":["US"],"source_country":"US",
            "is_active_observed":True,"explicit_is_active":status,
            "active_checked_at":NOW.isoformat(),"advertiser":"Doresty"}

class DeepV15Tests(unittest.TestCase):
    def test_threshold(self):
        _,ranking,candidates=d.aggregate([ad(i) for i in range(20)],NOW)
        self.assertEqual(len(ranking["beauty"]),0)
        self.assertEqual(candidates[0]["missing_to_21"],1)
        _,ranking,candidates=d.aggregate([ad(i) for i in range(21)],NOW)
        self.assertEqual(len(ranking["beauty"]),1)
        self.assertEqual(ranking["beauty"][0]["ad_count"],21)
    def test_duplicate_ids_and_different_products(self):
        ads=[ad(i) for i in range(20)]+[ad(1)]+[ad(99,"different-makeup-bag")]
        _,rank,candidates=d.aggregate(ads,NOW)
        self.assertFalse(rank["beauty"])
        self.assertEqual(len(candidates),2)
    def test_inactive_and_expired_not_counted(self):
        xs=[ad(i) for i in range(21)]
        xs[0]["explicit_is_active"]=False
        xs[1]["active_checked_at"]="2025-01-01T00:00:00+00:00"
        _,rank,candidates=d.aggregate(xs,NOW)
        self.assertFalse(rank["beauty"])
        self.assertEqual(candidates[0]["ad_count"],19)
    def test_country_and_pet_exclusion(self):
        xs=[ad(i) for i in range(21)]
        for row in xs: row["source_countries"]=["PH"]
        _,rank,_=d.aggregate(xs,NOW)
        self.assertFalse(rank["beauty"])
        self.assertIsNone(d.direct_product(ad(1,"pet-dog-hair-shampoo")))
    def test_focus_and_broad_search(self):
        c=[{"ad_count":16,"name":"standing makeup bag portable large capacity",
            "countries":["FI"],"category":"beauty",
            "product_url":"https://doresty.store/products/standing-makeup-bag-portable-large-capacity"}]
        planned,cursor,focus=d.planning({"cursor":0,"focus_cursor":0},c,12)
        self.assertEqual(len(planned),12)
        self.assertEqual(sum(x["mode"]=="focused" for x in planned),6)
        self.assertEqual(cursor,6)
        self.assertEqual(focus,6)
        self.assertTrue(all(x["country"] not in d.EXCLUDED_COUNTRIES for x in planned))
    def test_normalize_explicit_false(self):
        raw={"ad_archive_id":"1234567","is_active":False}
        self.assertIsNone(d.normalize(raw,{"country":"US"},NOW))
if __name__=="__main__":unittest.main()
