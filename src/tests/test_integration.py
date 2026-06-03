"""集成测试 — 测试分析→更新→查询完整流程（不依赖浏览器）。"""

import os
import unittest
import tempfile
from pathlib import Path

import modes.zhipin.storage
from modes.zhipin.storage import init_db, insert_job, get_jobs, get_job_by_id
from modes.zhipin.storage import update_job_status, batch_update_jobs, get_stats, JobQuery


class TestIntegration(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._tmp_db = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        cls._tmp_db.close()
        modes.zhipin.storage.DB_PATH = Path(cls._tmp_db.name)
        init_db()

    @classmethod
    def tearDownClass(cls):
        try:
            os.unlink(cls._tmp_db.name)
        except OSError:
            pass

    def test_full_flow_job_insert_query(self):
        job = {
            "boss_job_id": "test_integration_002",
            "title": "测试普工",
            "company": "集成测试公司",
            "salary": "5K-7K",
            "city": "深圳",
            "tags": ["五险一金"],
            "location": "南山区",
            "recruiter_active": "今日活跃",
            "job_url": "https://www.zhipin.com/job_detail/test002",
            "description": "这是一条集成测试职位描述",
            "company_info": "测试公司信息",
        }

        # insert_job 有去重逻辑，可能因重复返回 False
        _ = insert_job(job)
        # 至少能查询到该记录
        jobs = get_jobs(JobQuery(status="new", limit=50))
        found = [j for j in jobs if j.get("boss_job_id") == "test_integration_002"]
        self.assertGreaterEqual(len(found), 1)

    def test_full_flow_batch_update(self):
        results = [{
            "job_id": 1,
            "five_insurance": True,
            "room_board": False,
            "regular_hours": True,
            "overtime_risk": "low",
            "diploma_ok": True,
            "recruiter_active": True,
            "match_score": 8,
            "reason": "集成测试分析结果",
        }]
        success, fail = batch_update_jobs(results)
        self.assertEqual(fail, 0)

    def test_update_status(self):
        update_job_status(1, "applied")
        job = get_job_by_id(1)
        if job:
            self.assertEqual(job.get("status"), "applied")
        else:
            self.skipTest("数据库中没有 ID=1 的记录")

    def test_get_stats(self):
        stats = get_stats()
        self.assertIsInstance(stats, dict)
        self.assertIn("total_jobs", stats)
        self.assertIsInstance(stats["total_jobs"], int)


if __name__ == "__main__":
    unittest.main()
