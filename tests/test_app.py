import unittest
import dataclasses
from typing import List, Dict, Set, Any

from app import _to_dict

@dataclasses.dataclass
class SimpleDataclass:
    id: int
    name: str

@dataclasses.dataclass
class ComplexDataclass:
    simple: SimpleDataclass
    items: List[SimpleDataclass]
    tags: Set[str]
    metadata: Dict[str, Any]

class TestToDict(unittest.TestCase):
    def test_basic_types(self):
        self.assertEqual(_to_dict(1), 1)
        self.assertEqual(_to_dict("test"), "test")
        self.assertEqual(_to_dict(True), True)
        self.assertIsNone(_to_dict(None))

    def test_list(self):
        self.assertEqual(_to_dict([1, 2, 3]), [1, 2, 3])
        self.assertEqual(_to_dict(["a", "b"]), ["a", "b"])

    def test_dict(self):
        self.assertEqual(_to_dict({"a": 1, "b": 2}), {"a": 1, "b": 2})

    def test_set(self):
        result = _to_dict({1, 2, 3})
        self.assertIsInstance(result, list)
        self.assertCountEqual(result, [1, 2, 3])

    def test_dataclass(self):
        obj = SimpleDataclass(id=1, name="test")
        self.assertEqual(_to_dict(obj), {"id": 1, "name": "test"})

    def test_nested_dataclass(self):
        simple = SimpleDataclass(id=1, name="test")
        obj = ComplexDataclass(
            simple=simple,
            items=[SimpleDataclass(id=2, name="item1"), SimpleDataclass(id=3, name="item2")],
            tags={"tag1", "tag2"},
            metadata={"key": SimpleDataclass(id=4, name="meta")}
        )
        result = _to_dict(obj)

        self.assertEqual(result["simple"], {"id": 1, "name": "test"})
        self.assertEqual(result["items"], [{"id": 2, "name": "item1"}, {"id": 3, "name": "item2"}])
        self.assertCountEqual(result["tags"], ["tag1", "tag2"])
        self.assertEqual(result["metadata"], {"key": {"id": 4, "name": "meta"}})

if __name__ == "__main__":
    unittest.main()
