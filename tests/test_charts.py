import unittest
from charts import grouped,daily
class ChartTests(unittest.TestCase):
    def test_group_preserves_total(self):
        result=grouped({str(i):i for i in range(10)},4)
        self.assertEqual(len(result),4)
        self.assertEqual(sum(v for _,v in result),45)
    def test_daily_fills_gaps_in_order(self):
        self.assertEqual(daily({'2026-09-03':200,'2026-09-01':100}),[('2026-09-01',100),('2026-09-02',0),('2026-09-03',200)])
        self.assertEqual(daily({}),[])
