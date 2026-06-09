# SWE-bench 数据集统计

> 统计时间：2026-06-09  
> 数据来源：`Dataset/SWE-bench/` 与 `Dataset/SWE-bench_Lite/` 本地 Parquet 文件

## 概览

| 数据集 | Issue 总数 | 涉及仓库数 | 数据划分 |
|--------|-----------|-----------|---------|
| **SWE-bench** | 21,527 | 53 | train / dev / test |
| **SWE-bench_Lite** | 323 | 18 | dev / test |

说明：每条数据对应一个 **instance**（一个 GitHub Issue 修复任务），以 `instance_id` 唯一标识。Lite 是 SWE-bench 的子集，主要用于快速评测与开发迭代。

---

## SWE-bench

### 按划分统计

| 划分 | Issue 数 | 仓库数 | 用途 |
|------|---------|--------|------|
| train | 19,008 | 35 | 训练 / 检索增强 |
| dev | 225 | 6 | 开发验证 |
| test | 2,294 | 12 | 正式评测 |
| **合计** | **21,527** | **53** | — |

### test 划分（正式评测集，2,294 条）

| 仓库 | Issue 数 | 占比 |
|------|---------|------|
| django/django | 850 | 37.1% |
| sympy/sympy | 386 | 16.8% |
| scikit-learn/scikit-learn | 229 | 10.0% |
| sphinx-doc/sphinx | 187 | 8.2% |
| matplotlib/matplotlib | 184 | 8.0% |
| pytest-dev/pytest | 119 | 5.2% |
| pydata/xarray | 110 | 4.8% |
| astropy/astropy | 95 | 4.1% |
| pylint-dev/pylint | 57 | 2.5% |
| psf/requests | 44 | 1.9% |
| mwaskom/seaborn | 22 | 1.0% |
| pallets/flask | 11 | 0.5% |

### dev 划分（225 条）

| 仓库 | Issue 数 |
|------|---------|
| pvlib/pvlib-python | 63 |
| pydicom/pydicom | 56 |
| sqlfluff/sqlfluff | 50 |
| pylint-dev/astroid | 31 |
| pyvista/pyvista | 16 |
| marshmallow-code/marshmallow | 9 |

### train 划分（19,008 条，Top 20 仓库）

| 仓库 | Issue 数 |
|------|---------|
| pandas-dev/pandas | 5,049 |
| Qiskit/qiskit | 1,406 |
| huggingface/transformers | 1,058 |
| mesonbuild/meson | 954 |
| numpy/numpy | 937 |
| googleapis/google-cloud-python | 926 |
| pantsbuild/pants | 900 |
| conan-io/conan | 855 |
| django/django | 850 |
| ipython/ipython | 850 |
| pypa/pip | 686 |
| conda/conda | 629 |
| docker/compose | 597 |
| apache/airflow | 473 |
| wagtail/wagtail | 414 |
| PrefectHQ/prefect | 407 |
| sympy/sympy | 386 |
| Lightning-AI/lightning | 377 |
| pyca/cryptography | 344 |
| ray-project/ray | 342 |

train 划分其余 15 个仓库（Issue 数 ≤ 328）：google/jax、ytdl-org/youtube-dl、celery/celery、scikit-learn/scikit-learn、jupyterlab/jupyterlab、sphinx-doc/sphinx、matplotlib/matplotlib、dagster-io/dagster、pytest-dev/pytest、open-mmlab/mmdetection、pydata/xarray、scipy/scipy、astropy/astropy、twisted/twisted、gitpython-developers/GitPython 等。

### 全部 53 个来源仓库（按 Issue 总数降序）

| # | 仓库 | Issue 数 |
|---|------|---------|
| 1 | pandas-dev/pandas | 5,049 |
| 2 | Qiskit/qiskit | 1,406 |
| 3 | huggingface/transformers | 1,058 |
| 4 | mesonbuild/meson | 954 |
| 5 | numpy/numpy | 937 |
| 6 | googleapis/google-cloud-python | 926 |
| 7 | pantsbuild/pants | 900 |
| 8 | conan-io/conan | 855 |
| 9 | django/django | 850 |
| 10 | ipython/ipython | 850 |
| 11 | pypa/pip | 686 |
| 12 | conda/conda | 629 |
| 13 | docker/compose | 597 |
| 14 | apache/airflow | 473 |
| 15 | wagtail/wagtail | 414 |
| 16 | PrefectHQ/prefect | 407 |
| 17 | sympy/sympy | 386 |
| 18 | Lightning-AI/lightning | 377 |
| 19 | pyca/cryptography | 344 |
| 20 | ray-project/ray | 342 |
| 21 | google/jax | 328 |
| 22 | ytdl-org/youtube-dl | 312 |
| 23 | celery/celery | 250 |
| 24 | scikit-learn/scikit-learn | 229 |
| 25 | jupyterlab/jupyterlab | 201 |
| 26 | sphinx-doc/sphinx | 187 |
| 27 | matplotlib/matplotlib | 184 |
| 28 | dagster-io/dagster | 151 |
| 29 | pytest-dev/pytest | 119 |
| 30 | open-mmlab/mmdetection | 111 |
| 31 | pydata/xarray | 110 |
| 32 | scipy/scipy | 101 |
| 33 | astropy/astropy | 95 |
| 34 | twisted/twisted | 74 |
| 35 | gitpython-developers/GitPython | 68 |
| 36 | pvlib/pvlib-python | 63 |
| 37 | DataDog/integrations-core | 62 |
| 38 | pylint-dev/pylint | 57 |
| 39 | pydicom/pydicom | 56 |
| 40 | sqlfluff/sqlfluff | 50 |
| 41 | tensorflow/models | 50 |
| 42 | psf/requests | 44 |
| 43 | explosion/spaCy | 41 |
| 44 | pylint-dev/astroid | 31 |
| 45 | tiangolo/fastapi | 28 |
| 46 | mwaskom/seaborn | 22 |
| 47 | pyvista/pyvista | 16 |
| 48 | kubeflow/pipelines | 14 |
| 49 | pallets/flask | 11 |
| 50 | marshmallow-code/marshmallow | 9 |
| 51 | apache/mxnet | 5 |
| 52 | python/typeshed | 5 |
| 53 | JohnSnowLabs/spark-nlp | 3 |

---

## SWE-bench Lite

Lite 从 SWE-bench 中筛选而来，**仅保留 test / dev 划分**，无 train 集。test 集共 300 条（官方文档描述），dev 集 23 条。

### 按划分统计

| 划分 | Issue 数 | 仓库数 |
|------|---------|--------|
| test | 300 | 12 |
| dev | 23 | 6 |
| **合计** | **323** | **18** |

### test 划分（300 条）

| 仓库 | Issue 数 | 占比 |
|------|---------|------|
| django/django | 114 | 38.0% |
| sympy/sympy | 77 | 25.7% |
| matplotlib/matplotlib | 23 | 7.7% |
| scikit-learn/scikit-learn | 23 | 7.7% |
| pytest-dev/pytest | 17 | 5.7% |
| sphinx-doc/sphinx | 16 | 5.3% |
| astropy/astropy | 6 | 2.0% |
| psf/requests | 6 | 2.0% |
| pylint-dev/pylint | 6 | 2.0% |
| pydata/xarray | 5 | 1.7% |
| mwaskom/seaborn | 4 | 1.3% |
| pallets/flask | 3 | 1.0% |

### dev 划分（23 条）

| 仓库 | Issue 数 |
|------|---------|
| sqlfluff/sqlfluff | 5 |
| pvlib/pvlib-python | 5 |
| pylint-dev/astroid | 5 |
| pydicom/pydicom | 5 |
| marshmallow-code/marshmallow | 2 |
| pyvista/pyvista | 1 |

### 全部 18 个来源仓库（按 Issue 总数降序）

| # | 仓库 | Issue 数 |
|---|------|---------|
| 1 | django/django | 114 |
| 2 | sympy/sympy | 77 |
| 3 | matplotlib/matplotlib | 23 |
| 4 | scikit-learn/scikit-learn | 23 |
| 5 | pytest-dev/pytest | 17 |
| 6 | sphinx-doc/sphinx | 16 |
| 7 | astropy/astropy | 6 |
| 8 | psf/requests | 6 |
| 9 | pylint-dev/pylint | 6 |
| 10 | pvlib/pvlib-python | 5 |
| 11 | pydata/xarray | 5 |
| 12 | pydicom/pydicom | 5 |
| 13 | pylint-dev/astroid | 5 |
| 14 | sqlfluff/sqlfluff | 5 |
| 15 | mwaskom/seaborn | 4 |
| 16 | pallets/flask | 3 |
| 17 | marshmallow-code/marshmallow | 2 |
| 18 | pyvista/pyvista | 1 |

---

## 两个数据集对比

| 对比项 | SWE-bench | SWE-bench Lite |
|--------|-----------|----------------|
| Issue 总数 | 21,527 | 323 |
| 来源仓库数 | 53 | 18 |
| test 集 Issue 数 | 2,294 | 300 |
| test 集仓库数 | 12 | 12 |
| dev 集 Issue 数 | 225 | 23 |
| train 集 | 有（19,008 条） | 无 |
| 主要语言 | Python 为主 | Python 为主 |

**Lite test 集与 SWE-bench test 集的关系：** Lite 的 12 个 test 仓库与 SWE-bench test 的 12 个仓库完全一致，但每个仓库下的 Issue 数量更少（Lite 是对 test 集的精简子采样）。

**Lite 额外包含的 dev 仓库：** dev 划分中的 6 个仓库（pvlib、pydicom、sqlfluff、astroid、marshmallow、pyvista）来自 SWE-bench 的 dev 划分，不在 Lite 的 test 集中出现。

---

## 数据文件路径

```
Dataset/
├── SWE-bench/
│   └── data/
│       ├── train-00000-of-00001.parquet   # 19,008 条
│       ├── dev-00000-of-00001.parquet     # 225 条
│       └── test-00000-of-00001.parquet    # 2,294 条
└── SWE-bench_Lite/
    └── data/
        ├── dev-00000-of-00001.parquet     # 23 条
        └── test-00000-of-00001.parquet    # 300 条
```

每条 Issue 包含 12 个字段：`repo`、`instance_id`、`base_commit`、`patch`、`test_patch`、`problem_statement`、`hints_text`、`created_at`、`version`、`FAIL_TO_PASS`、`PASS_TO_PASS`、`environment_setup_commit`。
