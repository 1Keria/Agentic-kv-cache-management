"""Deterministic concurrency correctness checks, separate from timings."""
import threading
import time
import unittest

import numpy as np

from predictor import Node, Worker, reuse_probability, choose_candidate


class GatedModel:
    def __init__(self):
        self.block = False
        self.entered = threading.Event()
        self.release = threading.Event()

    def predict(self, snapshots):
        if self.block:
            self.entered.set()
            if not self.release.wait(5):
                raise RuntimeError("test gate timeout")
        p = np.full((len(snapshots), 10), .1)
        h = p[:, :9] / np.cumsum(p[:, ::-1], 1)[:, ::-1][:, :9]
        return p, h


class Tests(unittest.TestCase):
    def test_inflight_stale_queue_full_and_nonblocking(self):
        m = GatedModel()
        w = Worker(m, batch_size=1, capacity=1)
        try:
            m.block = True
            n = Node("X")
            raw = {"hits": 1}
            old = n.begin(raw)
            raw["hits"] = 99
            self.assertEqual(old.snapshot["hits"], 1)
            self.assertTrue(w.submit(old))
            self.assertTrue(m.entered.wait(2))
            new = n.begin({"hits": 2})
            self.assertTrue(w.submit(new))
            self.assertFalse(w.submit(Node("Y").begin({})))
            # The worker is provably blocked, while enqueue and eviction reads returned.
            self.assertFalse(m.release.is_set())
            self.assertIsNone(n.read())
            self.assertEqual(choose_candidate([n], 0), (n, False))
            m.release.set()
            w.close()
            self.assertIs(n.prediction_state, new)
            self.assertIsNotNone(n.read())
            self.assertEqual(choose_candidate([n], 0), (n, True))
            self.assertIsNone(old.result)
            self.assertEqual(w.dropped, 1)
            n.invalidate()  # deletion or re-lock
            self.assertIsNone(n.read())
        finally:
            m.release.set()
            if w.thread.is_alive():
                w.close()

    def test_interpolation_and_open_tail(self):
        p = np.full(10, .1)
        h = p[:9] / np.cumsum(p[::-1])[::-1][:9]
        self.assertAlmostEqual(reuse_probability(h, 0, 20), .5)
        self.assertAlmostEqual(reuse_probability(h, 5, 15), .2 / .7)
        self.assertEqual(reuse_probability(h, 4, 0), 0)
        self.assertIsNone(reuse_probability(h, 490, 20))
        values = [reuse_probability(h, 0, x / 10) for x in range(100)]
        self.assertTrue(all(a <= b for a, b in zip(values, values[1:])))


if __name__ == "__main__":
    unittest.main()
