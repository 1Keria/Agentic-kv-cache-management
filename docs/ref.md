cat > TASK.md <<'EOF'
你是 LLM serving systems 方向的代码审计员。请只读分析以下四个开源项目，不要修改源码：

- ./sglang
- ./vllm
- ./Mooncake
- ./lmcache

目标：分析这四个项目如何管理 KV cache。不要写泛泛综述，必须基于代码文件、类、函数、数据结构、调用链来说明。

请重点回答：

1. KV cache 的基本抽象
   - cache entry / block / page / segment / token range / prefix node 分别如何表示？
   - key 是什么？token ids、hash、prefix tree path、request id、block id，还是其他？
   - value 是什么？GPU tensor、CPU tensor、serialized tensor、remote object、metadata？

2. 生命周期
   - KV cache 什么时候 allocate？
   - prefill 阶段如何写入？
   - decode 阶段如何 append？
   - 什么时候命中复用？
   - 什么时候 evict/free/offload？
   - request 结束后 cache 是否保留？

3. 内存层级
   - GPU HBM
   - CPU DRAM
   - disk / SSD
   - remote memory / RDMA / distributed store
   - 每个项目分别支持哪些层级？

4. Prefix cache / reuse 机制
   - exact prefix match 还是 block hash？
   - 是否支持 partial hit？
   - 是否支持非 prefix 复用？
   - 是否支持跨请求、跨 worker、跨 engine、跨节点复用？

5. 调度器与 KV cache 的关系
   - scheduler 如何知道 cache 命中？
   - cache 命中如何影响 prefill / decode / batching？
   - KV cache 空间不足时如何影响 admission control / eviction / recompute？

6. 关键源码路径
   对每个项目列出最关键的文件、类、函数，并说明它们的职责。
   必须包含相对路径，例如：
   - sglang/...
   - vllm/...
   - Mooncake/...
   - lmcache/...

7. 横向对比
   输出一张 Markdown 表格，列包括：
   - 项目
   - KV cache 核心设计
   - 管理粒度
   - cache key
   - cache value
   - 内存层级
   - eviction 策略
   - 是否跨请求复用
   - 是否跨节点/跨 engine 复用
   - 主要优点
   - 主要限制

8. 画两个 Mermaid 图：
   - 单请求 prefill/decode 下 KV cache 写入与读取流程
   - 四个项目的 KV cache 架构对比图

9. 最后给出结论：
   - 如果我要自己设计一个 KV cache manager，应该分别借鉴这四个项目什么？
   - 哪些设计是 engine 内部 KV 管理，哪些是外部 KV 存储/传输层？
   - SGLang/vLLM 与 Mooncake/LMCache 的边界是什么？

工作方法要求：

- 先用 ripgrep 搜索关键词：
  kv_cache, kvcache, prefix, radix, block_manager, paged, cache_engine, eviction, offload, connector, transfer, store, prefill, decode
- 每个结论都要尽量给出源码路径依据。
- 不确定的地方必须标注“不确定”，并说明还需要看哪些文件。
- 最终输出到 ./KV_CACHE_STUDY.md。
- 同时输出一个 ./KV_CACHE_FILE_INDEX.md，专门列关键文件索引。
- 不要安装依赖，不要运行 GPU 测试，不要改源码。
EOF

cat > TASK_INDEX.md <<'EOF'
只读分析 ./sglang ./vllm ./Mooncake ./lmcache。

目标：不要写完整报告，只找出和 KV cache 管理相关的关键源码文件。

请用 ripgrep 搜索：
kv_cache, kvcache, prefix, radix, block_manager, paged, cache_engine, eviction, offload, connector, transfer, store, prefill, decode

输出 ./KV_CACHE_FILE_INDEX.md，格式：

# KV Cache File Index

## SGLang
| 文件 | 关键类/函数 | 作用 | 为什么相关 |

## vLLM
...

## Mooncake
...

## LMCache
...

不要修改源码，不要安装依赖，不要运行测试。
EOF

claude -p "$(cat TASK_INDEX.md)" --output-format stream-json --verbose | tee index.log

cat > TASK_REPORT.md <<'EOF'
请基于 ./KV_CACHE_FILE_INDEX.md 和四个源码目录，写完整报告 ./KV_CACHE_STUDY.md。

报告必须包含：
1. 每个项目的 KV cache 架构
2. KV cache 生命周期
3. prefix reuse / block reuse / offload / transfer / eviction 机制
4. 调度器与 KV cache 的关系
5. 横向对比表
6. 两个 Mermaid 图
7. 如果自研 KV cache manager，应该借鉴什么
8. SGLang/vLLM 与 Mooncake/LMCache 的边界

每个关键判断都要带源码路径。不要泛泛而谈。
EOF

claude -p "$(cat TASK_REPORT.md)" --output-format stream-json --verbose | tee report.log

上下文管理要求：

1. 你可能会遇到上下文压缩。不要依赖对话历史保存关键状态。
2. 每完成一个项目的初步分析，必须把阶段性结论写入磁盘：
   - ./notes/sglang.md
   - ./notes/vllm.md
   - ./notes/mooncake.md
   - ./notes/lmcache.md
3. 每发现一个关键源码文件，立即追加到：
   - ./KV_CACHE_FILE_INDEX.md
4. 每个阶段结束后，更新：
   - ./PROGRESS.md

./PROGRESS.md 必须包含：
- 已完成哪些项目
- 当前正在分析什么
- 下一步要做什么
- 已确认的关键文件
- 不确定项
- 最终报告还缺什么

如果发生上下文压缩，先重新读取：
- ./TASK.md
- ./PROGRESS.md
- ./KV_CACHE_FILE_INDEX.md
- ./notes/*.md
然后继续。

我要检查
SGLang:
- RadixAttention / radix tree / prefix cache
- KV memory pool
- HiCache / hierarchical cache / offload backend

vLLM:
- PagedAttention
- KV cache manager / block manager
- block table
- prefix caching / hash / eviction

Mooncake:
- Mooncake Store
- Transfer Engine
- KV cache object metadata
- distributed storage / RDMA / prefill-decode transfer

LMCache:
- connector
- vLLM/SGLang integration
- offload / lookup / retrieve / store
- CPU / disk / remote backend