# WildChat-1M（Request 侧明文）

来源：[allenai/WildChat-1M](https://huggingface.co/datasets/allenai/WildChat-1M)  
协议：[ODC-BY](https://opendatacommons.org/licenses/by/1-0/)（仓库内 `LICENSE.md`）

这是 **去毒公开版**（约 84 万对话 / 3.36 GB parquet），不是 gated 的 [WildChat-1M-Full](https://huggingface.co/datasets/allenai/WildChat-1M-Full)。

下载：

```bash
python scripts/python/download_wildchat.py
```

目录保持 HF 原路径：`data/train-00000-of-00014.parquet` … `00013`。

下载完成（2026-08-18）：**14** 个 parquet + `LICENSE.md`，约 **3.13 GB**，校验通过。

用途：和 SkillsBench Flash with-skills 混跑时，作为普通人请求的 **正文 + 会话内时间**。转换脚本另写；不要整库原样打进 serving。
