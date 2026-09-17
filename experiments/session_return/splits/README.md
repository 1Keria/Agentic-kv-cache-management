# GLM Session 返回时间切分

数据：`third_party/glm-5dot1_onlinedata/glm-5dot1_onlinedata_lt32k.jsonl`  
生成：`python scripts/python/split_glm_session_return.py`

按 `start_time` 排序后切 70/15/15，不按 user hash。

```text
splits/
  manifest.json
  README.md
  full/                  全量正式实验
    train.jsonl          11591
    val.jsonl            2484
    test.jsonl           2484
  small/                 小型测试（时间前缀 2200 条，都在 full train 里）
    train.jsonl          1540
    val.jsonl            330
    test.jsonl           330
```

标签：`tau_s_full` / `delta_full` 是到下一次同 hash、messages 严格前缀增长的到达间隔（秒）；若下一次落在本折窗口之外则右删失到切点。小型折用 `tau_s_small` / `delta_small`。

重放按到达顺序，也就是 `train.jsonl` + `val.jsonl` + `test.jsonl`。`small` 的 val/test 不是正式 val/test。
