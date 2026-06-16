# vLLM 源码编译安装记录

> 日期：2026-06-16
> 环境：8× H800 (80GB), NVIDIA Driver 550.90.07 (CUDA 12.4)

---

## 1. 环境现状

| 项目 | 值 | 问题 |
|------|-----|------|
| GPU | 8× H800 (80GB each) | ✅ |
| NVIDIA Driver | 550.90.07 → 最高支持 CUDA 12.4 | ⚠️ |
| conda env | `agentkv_zls` (Python 3.11) | ✅ |
| PyTorch | 2.11.0+cu130 (编译 CUDA 13.0) | ⚠️ 驱动只支持 12.4 |
| vLLM 源码 | `Engine/vllm/` (要求 torch==2.11.0) | ✅ |
| 模型 | Qwen3-8B (本地) | ⚠️ 权重文件不完整（缺 layer 28-35） |

---

## 2. 关键发现：CUDA forward compatibility

**PyTorch cu130 在 CUDA 12.4 驱动上不可用**，但系统安装了 CUDA compat 库：

```
/usr/local/cuda-13.0/compat/libcuda.so.580.95.05
/usr/local/cuda-13/compat/libcuda.so.580.95.05
/usr/local/cuda/compat/libcuda.so.580.95.05
```

**解决方案**：设置 `LD_LIBRARY_PATH` 加载 compat 库，PyTorch cu130 即可正常使用 GPU：

```bash
export LD_LIBRARY_PATH=/usr/local/cuda-13.0/compat:$LD_LIBRARY_PATH
```

验证结果：
```python
torch.cuda.is_available() → True
torch.cuda.device_count() → 8
```

**这意味着不需要降级 PyTorch 或新建 env，直接在现有 `agentkv_zls` 环境中编译安装 vLLM 即可。**

---

## 3. 编译安装过程

### 3.1 安装方式

从源码 editable install（方便后续改代码）：

```bash
pip install -e . --no-build-isolation
```

### 3.2 遇到的三个问题及解决方案

#### 问题 1：setuptools-scm 版本检测失败

**现象**：
```
LookupError: setuptools-scm was unable to detect version for Engine/vllm.
However, a repository was found in a parent directory: /share/dai-sys/zhoulongsheng/agentkv
```

**原因**：vLLM 源码位于 `agentkv` 项目的子目录中，`setuptools-scm` 检测到父目录的 git repo，但父目录的 git tag 与 vLLM 无关，导致版本检测失败。

**尝试过的方案**：
1. `SETUPTLE_SCM_PRETEND_VERSION` 环境变量 → ❌ 不生效（vcs_versioning 包忽略此变量）
2. `[tool.setuptools_scm] search_parent_directories = true` → ❌ 不生效（父目录 git tag 不匹配）
3. `VLLM_VERSION_OVERRIDE` 环境变量 → ️ 不生效（内部仍调用 `get_version()`）

**最终方案**：修改 `setup.py` 中的 `get_vllm_version()` 函数，返回硬编码版本号：

```python
# 原代码 (setup.py:987-995):
def get_vllm_version() -> str:
    if env_version := os.getenv("VLLM_VERSION_OVERRIDE"):
        print(f"Overriding VLLM version with {env_version} from VLLM_VERSION_OVERRIDE")
        os.environ["SETUPTOOLS_SCM_PRETEND_VERSION"] = env_version
        return get_version(write_to="vllm/_version.py")

    version = get_version(write_to="vllm/_version.py")
    ...

# 修改为:
def get_vllm_version() -> str:
    # AgentKV local dev: bypass setuptools-scm (fails in nested git repo)
    _LOCAL_VERSION = "0.8.5.dev0"
    with open("vllm/_version.py", "w") as f:
        f.write(f"__version__ = version = '{_LOCAL_VERSION}'\n")
    return _LOCAL_VERSION
```

同时修改 `pyproject.toml`，将 version 从 dynamic 改为静态：

```python
# 原代码:
dynamic = [ "version", "dependencies", "optional-dependencies"]

# 修改为:
version = "0.8.5.dev0"
dynamic = [ "dependencies", "optional-dependencies"]
```

#### 问题 2：CMake 缓存指向旧路径

**现象**：
```
CMake Error: The current CMakeCache.txt directory .../Engine/vllm/.deps/cutlass-subbuild/CMakeCache.txt
is different than the directory .../repos/serving_frameworks/vllm/.deps/cutlass-subbuild
where CMakeCache.txt was created.
```

**原因**：之前 vLLM 源码位于 `repos/serving_frameworks/vllm/`，后来移动到 `Engine/vllm/`。CMake 缓存仍指向旧路径。

**解决方案**：清理所有构建缓存：

```bash
rm -rf Engine/vllm/.deps/
rm -rf Engine/vllm/build/
rm -rf Engine/vllm/dist/
rm -rf Engine/vllm/*.egg-info/
```

#### 问题 3：依赖冲突（vLLM vs SGLang）

**现象**：
```
sglang requires llguidance<0.8.0,>=0.7.11, but you have llguidance 1.7.6
sglang requires tilelang==0.1.8, but you have tilelang 0.1.9
sglang requires tokenspeed_mla==0.1.1, but you have tokenspeed-mla 0.1.2
```

**原因**：vLLM 和 SGLang 的依赖版本冲突。vLLM 安装时覆盖了 SGLang 的依赖。

**处理方式**：暂时不处理。vLLM 和 SGLang 不会同时运行同一个实验，所以冲突不影响功能。如果后续需要同时使用，可以在不同的 conda env 中隔离。

### 3.3 安装结果

```
Successfully built vllm
Successfully installed vllm-0.8.5.dev0
```

验证：
```python
import vllm
print(vllm.__version__)  # 'dev' (因为我们硬编码了版本号)
torch.cuda.is_available()  # True (8 GPU)
torch.cuda.get_device_name(0)  # 'NVIDIA H800'
```

---

## 4. Qwen3-8B 模型加载失败

### 4.1 现象

```
ValueError: Following weights were not initialized from checkpoint:
{'model.layers.27.input_layernorm.weight', 'model.layers.28.self_attn.q_norm.weight', ...}
```

缺了 layers 27-35 的所有权重（共 9 层）。

### 4.2 原因

Qwen3-8B 的 safetensors 文件**不完整**：

```
model-00001-of-00005.safetensors: layers 0-7
model-00002-of-00005.safetensors: layers 7-17
model-00003-of-00005.safetensors: layers 17-27
model-00005-of-00005.safetensors: 1 key (不含 layer)
# 缺 model-00004-of-00005.safetensors！
```

config.json 声明 36 层，但权重文件只覆盖到 layer 27。**缺少 shard 文件 `model-00004-of-00005.safetensors`**。

### 4.3 解决方案

重新完整下载 Qwen3-8B（清理旧的不完整文件）：

```bash
# 清理旧模型
rm -rf /share/dai-sys/.cache/hub/models--Qwen--Qwen3-8B/

# 启动 VPN 代理
vpn-start
export http_proxy=http://127.0.0.1:7890
export https_proxy=http://127.0.0.1:7890

# 用 hf 命令下载（注意：huggingface-cli 已弃用，要用 hf）
hf download Qwen/Qwen3-8B
```

下载耗时约 20 分钟（~16GB），模型存放在：
```
/share/dai-sys/.cache/hub/hub/models--Qwen--Qwen3-8B/snapshots/b968826d9c46dd6066d109eabc6255188de91218/
```

验证结果：
```
总 key 数: 399
层数: 36, 范围: 0-35
✅ 模型权重完整！所有 36 层都在
```

vLLM 加载测试通过：
```python
from vllm import LLM, SamplingParams
llm = LLM(model=MODEL_PATH, tensor_parallel_size=1, max_model_len=4096, gpu_memory_utilization=0.5)
output = llm.generate(['Hello, how are you?'], SamplingParams(max_tokens=20, temperature=0))
# 输出正常 ✅
```

---

## 5. 修改的源码文件清单

| 文件 | 修改内容 | 目的 |
|------|---------|------|
| `Engine/vllm/setup.py:987-995` | `get_vllm_version()` 返回硬编码 `"0.8.5.dev0"` | 绕过 setuptools-scm 版本检测失败 |
| `Engine/vllm/pyproject.toml:36` | 添加 `version = "0.8.5.dev0"`，从 dynamic 列表移除 `"version"` | 配合 setup.py 的静态版本 |
| `Engine/vllm/pyproject.toml:[tool.setuptools_scm]` | 添加注释说明本地 dev 修改 | 记录为什么禁用 scm |

---

## 6. 环境启动命令

```bash
# 必须设置 LD_LIBRARY_PATH 才能使用 GPU
export LD_LIBRARY_PATH=/usr/local/cuda-13.0/compat:$LD_LIBRARY_PATH

# 启动 vLLM API server
/share/dai-sys/apps/anaconda3/envs/agentkv_zls/bin/python -m vllm.entrypoints.openai.api_server \
  --model <MODEL_PATH> \
  --enable-prefix-caching \
  --gpu-memory-utilization 0.9 \
  --max-model-len 32768 \
  --port 8000
```

**注意**：所有涉及 vLLM 的命令都需要先 `export LD_LIBRARY_PATH=/usr/local/cuda-13.0/compat:$LD_LIBRARY_PATH`，否则 GPU 不可用。
