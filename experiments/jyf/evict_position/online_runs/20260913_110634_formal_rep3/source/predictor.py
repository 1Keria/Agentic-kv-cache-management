"""Shared seconds predictor and log-survival conditioning; immutable futures."""
import time
from concurrent.futures import ThreadPoolExecutor
import numpy as np
import torch
from training_base import ALL_NAMES, HazardNet, EDGES

class Model:
    def __init__(self, path):
        torch.set_num_threads(1)
        c = torch.load(path, map_location='cpu', weights_only=False)
        assert list(c['edges']) == list(EDGES)
        self.mean, self.std = c['mean'], c['std']
        self.mask = np.array([n in c['names'] for n in ALL_NAMES])
        self.net = HazardNet(len(ALL_NAMES)).eval()
        self.net.load_state_dict(c['state_dict'])
    def predict(self, rows):
        x = np.asarray(rows, np.float32)
        z = (x-self.mean)/self.std
        z[:,~self.mask] = 0
        with torch.inference_mode():
            result = torch.sigmoid(self.net(torch.from_numpy(z))).numpy().astype(np.float64)
        assert np.isfinite(result).all()
        return result

class Worker:
    def __init__(self, model, on_done=None):
        self.model = model
        self.on_done = on_done
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='hazard')
    def submit(self, rows):
        # One future per batch, no unbounded per-node task scheduling.
        return self.pool.submit(self.run, rows)
    def run(self, rows):
        start = time.perf_counter()
        h = self.model.predict(rows)
        elapsed = time.perf_counter()-start
        if self.on_done is not None:self.on_done(len(rows),elapsed)
        return h, elapsed
    def close(self):
        self.pool.shutdown(wait=True)

def log_survival(h, times):
    times = np.asarray(times, np.float64)
    edges = np.asarray(EDGES)
    left = np.r_[0., edges[:-1]]
    fractions = np.clip((times[...,None]-left)/(edges-left),0,1)
    return (fractions*np.log1p(-np.clip(h,1e-9,1-1e-9))).sum(-1)

def values(hazards, ages, path_tokens, node_tokens):
    # Fixed before serving: focus on the next minute, half-life 20s.
    # Beyond 60s has zero discount; no arbitrary interpolation in the infinite tail.
    b = np.array([0.,2.,5.,10.,20.,60.])
    ages = np.asarray(ages)
    assert (ages>=0).all() and (ages+60<=EDGES[-1]).all(), 'prediction exceeded defined finite domain'
    log_s = log_survival(np.asarray(hazards)[:,None,:], ages[:,None]+b[None,:])
    conditional_s = np.exp(log_s-log_s[:,:1])
    probs = np.maximum(0.,conditional_s[:,:-1]-conditional_s[:,1:])
    discount = 2**(-((b[:-1]+b[1:])/2)/20.)
    # Within each Full/SWA pool, bytes/token is constant and cancels in ranking.
    return np.asarray(path_tokens)/np.maximum(1,np.asarray(node_tokens))*(probs@discount)
