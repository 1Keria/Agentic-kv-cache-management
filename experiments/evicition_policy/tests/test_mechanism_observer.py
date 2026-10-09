import ast
import importlib.util
import io
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


observer = load("mechanism_observer")
installer = load("prepare_mechanism_observer")


class StripObservation(ast.NodeTransformer):
    def visit_ImportFrom(self, node):
        return None if node.module and node.module.endswith("mechanism_observer") else node

    def visit_Expr(self, node):
        return None if "agentkv_observer" in ast.unparse(node) else self.generic_visit(node)

    def visit_Assign(self, node):
        return None if "agentkv_observer" in ast.unparse(node) else self.generic_visit(node)

    def visit_FunctionDef(self, node):
        node = self.generic_visit(node)
        for i in range(len(node.body) - 1):
            first, second = node.body[i:i + 2]
            if (isinstance(first, ast.Assign) and isinstance(first.value, ast.Call)
                    and isinstance(first.value.func, ast.Attribute)
                    and first.value.func.attr == "_match_post_processor"
                    and isinstance(second, ast.Return)
                    and isinstance(second.value, ast.Name) and second.value.id == "result"):
                node.body[i:i + 2] = [ast.Return(value=first.value)]
                break
        return node


class Key:
    def __init__(self, tokens):
        self.token_ids = tokens
        self.extra_key = None

    def __len__(self):
        return len(self.token_ids)

    def __getitem__(self, index):
        return Key(self.token_ids[index])

    def child_key(self, page_size):
        return tuple(self.token_ids[:page_size])

    def match(self, other, page_size):
        count = 0
        for a, b in zip(self.token_ids, other.token_ids):
            if a != b:
                break
            count += 1
        return count // page_size * page_size


def fixture():
    root = SimpleNamespace(id=0, key=Key([]), parent=None, children={})
    node = SimpleNamespace(id=1, key=Key([1, 2, 3, 4]), parent=root, children={},
                           hit_count=1, last_access_time=1,
                           component_data={0: SimpleNamespace(value=[1, 2, 3, 4], lock_ref=0),
                                           1: SimpleNamespace(value=[1, 2, 3, 4], lock_ref=0)})
    root.children[node.key.child_key(2)] = node
    node.evicted = False
    cache = SimpleNamespace(root_node=root, page_size=2, sliding_window_size=4,
                            evictable_device_leaves=())
    obs = observer.MechanismObserver.__new__(observer.MechanismObserver)
    obs.cache = cache
    obs.enabled = obs.supported = True
    obs.full_ct, obs.swa_ct = 0, 1
    obs.seq = obs.reclaim_seq = obs.step = 0
    obs.reclaim_id = obs.driver = None
    obs.identities = {}
    obs.defined_pages = set()
    obs.full_history = set()
    obs.swa_history = set()
    obs.last_free = {"full": {}, "swa": {}}
    obs.stream = io.StringIO()
    return obs, node


class ObserverTests(unittest.TestCase):
    def test_namespace_and_page_alignment(self):
        namespace, pages = observer.page_chain([1, 2, 3, 4, 5], 2)
        self.assertEqual(len(pages), 2)
        self.assertEqual((namespace, pages), observer.page_chain([1, 2, 3, 4], 2))
        self.assertNotEqual(pages, observer.page_chain([1, 2, 3, 4], 2, "other")[1])
        self.assertEqual(pages[:1], observer.page_chain([1, 2], 2)[1])

    def test_history_requires_consecutive_swa_window(self):
        full = set("abcd")
        self.assertEqual(observer.history_match(list("abcd"), full, set("ad"), 256, 512), (1024, 256))
        self.assertEqual(observer.history_match(list("abcd"), full, set("acd"), 256, 512), (1024, 1024))
        self.assertEqual(observer.history_match(list("abcde"), full, full, 256, 512), (1024, 1024))

    def test_history_retains_actual_swa_materialization_after_free(self):
        obs, node = fixture()
        params = SimpleNamespace(swa_evicted_seqlen=0, chunked=False)
        obs.inserted(node.key, params, SimpleNamespace(prefix_len=0))
        obs.reclaim_id, obs.driver, obs.step = 1, "swa", 1
        node.component_data[1].value = None
        obs.freed(node, "swa", 4)
        req = SimpleNamespace(rid="test", origin_input_ids=[1, 2, 3, 4], output_ids=[])
        obs.matched(node.key, SimpleNamespace(req=req), SimpleNamespace(device_indices=[]))
        event = json.loads(obs.stream.getvalue().splitlines()[-1])
        self.assertEqual(event["historical_joint_tokens"], 4)
        self.assertEqual(event["inspected_full_tokens"], 4)
        self.assertEqual(event["history_shortfall_tokens"], 4)
        self.assertTrue(event["inspected_match_agrees"])
        self.assertEqual(event["swa_holes"][0]["last_free"]["driver"], "swa")
        obs.flush()
        self.assertFalse(obs.full_history)
        self.assertFalse(obs.swa_history)

    def test_tombstones_are_not_added_to_swa_history(self):
        obs, node = fixture()
        node.component_data[1].value = None
        obs.inserted(node.key, SimpleNamespace(swa_evicted_seqlen=4, chunked=False), SimpleNamespace(prefix_len=0))
        self.assertTrue(obs.full_history)
        self.assertFalse(obs.swa_history)

    def test_node_identity_survives_split(self):
        obs, child = fixture()
        before = obs.identity(child).copy()
        parent = SimpleNamespace(id=2, key=Key([1, 2]), parent=child.parent)
        child.parent = parent
        child.key = Key([3, 4])
        self.assertEqual(obs.identity(child), before)
        self.assertEqual(len(obs.segment_pages(child)), 1)
        self.assertEqual(obs.identity(parent)["end_page"], before["pages"][0])

    def test_removing_hooks_restores_all_official_asts(self):
        lock = json.loads((ROOT / "configs/environment.lock.json").read_text())
        with zipfile.ZipFile(ROOT / lock["engine"]["wheel"]) as wheel:
            for relative, patcher in (("unified_radix_cache.py", installer.patch_unified),
                                      ("unified_cache_components/full_component.py", installer.patch_full),
                                      ("unified_cache_components/swa_component.py", installer.patch_swa)):
                with self.subTest(file=relative):
                    source = wheel.read("sglang/srt/mem_cache/" + relative).decode()
                    original = ast.parse(source)
                    observed = StripObservation().visit(ast.parse(patcher(source)))
                    self.assertEqual(ast.dump(original), ast.dump(observed))


if __name__ == "__main__":
    unittest.main()
