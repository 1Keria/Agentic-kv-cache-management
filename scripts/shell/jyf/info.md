# Info About the Scripts

## mlp_reuse_offline.py
- used for prefix data 
- use rolling hash to build relation for messages
- for each `prefix_id`, record meta data such as `last_t`, `gaps`, `hit`, `pending`
- output in `/share/dai-sys/zhoulongsheng/agentkv/experiments/jyf/nn_exp/mlp_exp/data/prefix_reuse_samples.npz`
