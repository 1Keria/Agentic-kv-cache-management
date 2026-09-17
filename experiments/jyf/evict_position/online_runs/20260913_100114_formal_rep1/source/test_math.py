"""Analytic survival/censoring checks independent of trained weights."""
import numpy as np
import torch
from predictor import values,log_survival,Worker
from training_base import EDGES,hazard_loss

edges=np.array(EDGES)
h=1-np.exp(-.01*np.diff(np.r_[0,edges]))
bins=np.array([0.,2.,5.,10.,20.,60.])
expected=np.sum((np.exp(-.01*bins[:-1])-np.exp(-.01*bins[1:]))*2**(-((bins[:-1]+bins[1:])/2)/20))
actual=values(np.tile(h,(3,1)),[0.,20.,40.],[10,10,20],[10,10,10])
np.testing.assert_allclose(actual,[expected,expected,expected*2],rtol=1e-8)
assert np.all(np.diff(log_survival(h,np.arange(0,100)))<=0)
try:values(h[None,:],[7200.],[1],[1])
except AssertionError:pass
else:raise AssertionError('undefined tail extrapolated')

logits=torch.full((1,9),float(np.log(.2/.8)))
ed=torch.tensor(EDGES)
event=hazard_loss(logits,torch.tensor([3.]),torch.tensor([1.]),ed)
censor=hazard_loss(logits,torch.tensor([3.]),torch.tensor([0.]),ed)
np.testing.assert_allclose(event.item(),-np.log(.8)-np.log(.2),rtol=1e-6)
np.testing.assert_allclose(censor.item(),-(1+1/3)*np.log(.8),rtol=1e-6)

class Fake:
    calls=0
    def predict(self,rows):
        self.calls+=1
        if rows==['bad']:raise ValueError('intentional')
        return rows
m=Fake()
w=Worker(m)
f=w.submit([1,2])
assert f.result()[0]==[1,2] and f.result()[0]==[1,2] and m.calls==1
try:w.submit(['bad']).result()
except ValueError:pass
else:raise AssertionError('worker error was hidden')
w.close()
print('PASS analytic conditional survival, value scaling, censor loss, future reuse and failure propagation')
