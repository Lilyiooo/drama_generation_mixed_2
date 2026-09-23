import json
import tempfile
import unittest
from pathlib import Path

from service.drama_by_creativity.tests.run_test import load_creativity_input


class CreativityInputTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def write(self, payload):
        path = self.root / "input.json"
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return path

    def test_load_creativity_input_uses_explicit_fields(self):
        path = self.write(
            {
                "sample_id": "sample-1",
                "core_story": "核心故事",
                "topic": "悬疑",
                "world_view": "世界观",
                "role_setting": "人物设定",
            }
        )
        result = load_creativity_input(str(path))
        self.assertEqual(result["sample_id"], "sample-1")
        self.assertEqual(result["core_story"], "核心故事")
        self.assertEqual(result["topic"], "悬疑")
        self.assertEqual(result["world_view"], "世界观")
        self.assertEqual(result["role_setting"], "人物设定")
        self.assertEqual(result["reference"], "")

    def test_load_creativity_input_rejects_empty_required_field(self):
        path = self.write(
            {
                "core_story": "核心故事",
                "topic": "悬疑",
                "world_view": "世界观",
                "role_setting": " ",
            }
        )
        with self.assertRaisesRegex(ValueError, "role_setting"):
            load_creativity_input(str(path))


if __name__ == "__main__":
    unittest.main()
