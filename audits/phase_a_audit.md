# 阶段 A 审计报告

**审计对象**：提交 `0b1652e`（`feat(packaging): 阶段A - 依赖单一真源 + wheel 携带 Web 资源 + 基线快照`）
**审计范围**：8 个文件 —— `pyproject.toml`、`setup.py`、`requirements.txt`、`.gitignore`、`tools/baseline.py`、`tools/verify_install.py`、`tests/conftest.py`、`tests/test_packaging.py`
**审计员**：phase-a-auditor（独立审计，只读仓库）
**审计时间**：2026-10-03 13:52–14:1x
**环境**：Windows / `C:\Python314\python.exe` = Python 3.14.3；setuptools 82.0.1（系统）/ 84.0.0（build 隔离）；pytest 9.1.1；starlette 1.0.0；fastapi 0.136.1；httpx 0.28.1；numpy 2.4.3；pandas 3.0.2

## 0. 审计基准冻结（重要）

审计期间工作树被其他成员并发修改，因此**所有证据均取自 `git archive 0b1652e` 导出的冻结副本**，而不是活动工作树：

- 冻结目录：`C:\Users\asus\AppData\Local\Temp\niche_audit\after`（= `0b1652e`）、`...\before`（= `89081fd`）
- 我逐一校验了 8 个受审文件在「活动工作树」与「提交 0b1652e」中的 SHA256：**8/8 完全一致**（`pyproject.toml` F9368F1B4E7F、`setup.py` C416E9BE284E、`requirements.txt` D6AC554018E5、`.gitignore` CDC903B38910、`tools/baseline.py` 5C0CD085DC32、`tools/verify_install.py` 7FD610D4B54B、`tests/conftest.py` F6CFC1630990、`tests/test_packaging.py` 2A603F66CB87），故本文行号可直接用于当前工作树。
- 审计期间实测到的并发写入（供 Lead 注意，**不属于本次审计结论**）：
  - 13:54:40 `git status --short` → ` M family_abm/core/simulation.py`、` M family_abm/fitting/fitter.py`
  - 13:5x → 追加 ` M family_abm/web/app.py`、`?? tests/test_simulation_and_fitting.py`
  - 13:59:59 `family_abm.egg-info` 被再次改写（他人再次在仓库内跑构建/测试）
  - 最终 HEAD 已前移到 `47fbdff feat(core,fitting): 阶段B - 记录 t=0 基线 + 拟合输入显式化`（阶段 B，不在本次范围）
- 我**没有**在仓库内执行任何构建、安装或测试（所有构建都在 TEMP 副本中完成），本报告是本次审计对仓库唯一的写入。

---

## 1. 判定汇总表

| 断言 | 判定 | 我的实测 | 声称值 | 差异 |
|---|---|---|---|---|
| **V1** pyproject 依赖覆盖 `import family_abm` 全部第三方依赖，无遗漏/多余 | **部分成立** | AST 扫描 `family_abm`：直接第三方导入 = numpy, pandas, scipy, matplotlib, fastapi, uvicorn, pydantic + `networkx`（仅在 `viz/plots.py:200-203` 函数内惰性导入）；`jinja2` 无直接导入但在 `web/app.py:9` 经 starlette 传递必需。声明 9 项 → **无遗漏**；但 `networkx` 非 `import family_abm` 必需（**多余**），`httpx` 未进 `dev` extra（**缺口**） | “声明全部 9 个运行时依赖…根据：web/app.py 依赖 pydantic” | 无遗漏 ✓；多余 1 项；httpx 治理缺口 |
| **V2** wheel 真含 `web/templates/index.html`、`static/css/style.css`、`static/js/dashboard.js`，无资源漏掉 | **成立** | 自行构建 wheel：**41676 B / 33 entries**，3 个资源全在；仓库 `family_abm/web/` 下实际只有 **3** 个非 .py 文件（1 模板 + 2 静态），与 wheel 内 3 个一一对应，**无遗漏**；`tests/`、`tools/` 未进 wheel | “templates 与 static 均收录” | 无 |
| **V3** `verify_install.py` 是有效回归测试，不是永远绿色 | **部分成立** | 反证全部按预期变红：删 `templates/` → exit 1（2 项 FAIL，含 `TemplateNotFound`）；删 `static/` → exit 1（`RuntimeError: Directory ... does not exist`）；只删 `dashboard.js` → exit 1；`app.py` 导入抛错 → exit 1；旧 wheel(0.1.0) → exit 1。**但**：TestClient 导入链抛**普通 `ImportError`** 时脚本打印 `[SKIP]` 后 `结果：全部通过` **exit 0**，`pytest` 仍报 **PASSED**（§3 CE5/CE9 实证假绿） | “反证立即 FAIL 且退出码 1” | 反证成立；存在 1 条假绿路径 |
| **V4** `test_packaging.py` 无恒真/过弱断言、无过宽 skip | **部分成立** | 存在：① 真空断言 `baseline/__init__.py` 不存在（`test_packaging.py:76-79`，该目录本就不存在）；② 依赖清单为硬编码 9 名（`:24`），不做源码交叉验证；③ 2 处过宽 skip（`:101`、`:113`）实测可令 **6 passed / 3 skipped / exit 0**，3 条打包回归测试整体消失；④ 组合假绿（§3 CE9）下 9 项全绿 | “新增 tests/test_packaging.py（9 项）” | 测试有效但不完备 |
| **V5** baseline 可复现性真实；uuid4 是否埋跨进程不可复现隐患 | **成立（并已澄清 uuid）** | 5 个独立进程同 seed → **同一 SHA256 `3C2D46368EDF68F1`，逐字节相同（2654 B）**；seed 7 → 不同（`70DFEDCB58459A77`）。JSON 只含 `seed/steps/summary`，**不含 `agent_id`**；把 `uuid.uuid4` 换成递增/递减确定性 id 后两次输出与真 uuid 运行**字节相同** → uuid 对快照零影响（依据：`ml/recorder.py:28` 确实记录 `agent_id`，但 `tools/baseline.py:59` 的 `select_dtypes(include=[np.number])` 把该字符串列剔除；且 `core/environment.py:15,28-29` 按插入序遍历，无 id 排序） | “同一脚本可复现” | 成立；隐患边界已定位 |
| **V6** 三个数字：27693 B/30 → 41676 B/33、“9 passed”、“反证立即 FAIL 且退出码 1” | **部分成立** | **41676 B / 33 entries：完全复现**；**“9 passed”：完全复现**（`9 passed in 32.85s`）；反证 exit 1：完全复现。**27693 B 需 `--no-isolation`（setuptools 82.0.1）才能得到；隔离构建为 27695**。而 41676 来自隔离构建（setuptools 84.0.0），非隔离为 41675 → 声称的一对 (27693, 41676) **不是同一工具链**，同工具链应为 (27693, 41675) 或 (27695, 41676)；entries 30→33 两种工具链都一致 | “27693 B / 30 entries 变为 41676 B / 33 entries” | 关键 3 项数字全对；before/after 字节口径不一致（±1 B） |
| **V7** `setup.py` 薄壳后 `--version` / `-e .` / `python -m build` 仍正常；双重声明冲突风险 | **成立（附 2 条注意）** | `python setup.py --version` → `0.2.0` exit 0；`--name` → `family_abm` exit 0；`python -m build`（sdist+wheel）exit 0；`pip install -e .` exit 0 且 editable 导入正常、`importlib.metadata.version` = 0.2.0。冲突实验：在 setup.py 写 `install_requires=["numpy>=9.9.9"], packages=["family_abm","tests"]` → 构建 exit 0 **且无任何冲突告警**，METADATA 仍为 pyproject 的 9 项、wheel 无 `tests/` → **pyproject 静默胜出** | “setup.py 改为薄壳…不再重复声明元数据” | 功能成立；静默忽略是新的脚枪 |
| **额外** 仓库根是否被构建/测试污染 | **不成立（存在污染）** | `git status --short` = **空**（新增文件在 `audits/`，本节实测于写入前）；但 `git status --short --ignored` 含 `build/`、`family_abm.egg-info/`、9 个 `__pycache__/`。`build/` 创建时间 **2026/10/3 13:52:50**、`family_abm.egg-info` 最后写入 **13:52:50**（提交时间 13:53:26）→ 由提交前的测试运行产生；我在 TEMP 副本跑一次 `pytest tests/` 后同样得到 `build/` + `family_abm.egg-info/` → **测试自身污染 REPO_ROOT**（并违反本仓库 `audits/remediation_plan.md:292` “不得写仓库内的非 temp 路径”）。无 `dist/`、无 `.pytest_cache`、无 `baseline/` | “不污染” | 存在污染，且可复现归因 |
| **额外** `tools/`、`tests/` 是否进 wheel | **成立（未进）** | 解包 wheel：33 entries，无任何 `tests/`、`tools/` 前缀 | “避免 tests/ 与 tools/ 被装进 wheel” | wheel ✓；**sdist 仍含 `tests/test_packaging.py`**（55 项），缺 `conftest.py`、`tools/` |
| **额外** `license = { text = "MIT" }` 与仓库实际是否一致 | **不成立（不一致）** | `Test-Path LICENSE` = False、`Test-Path LICENSE.txt` = False、`git ls-files \| grep -i license` 为空、README 无 License 章节；构建时 setuptools 打印 `SetuptoolsDeprecationWarning: `project.license` as a TOML table is deprecated … By 2027-Feb-18, you need to update your project and remove deprecated calls or your builds will no longer be supported.` | 未声称 | 声明 MIT 但无 LICENSE 文件 + PEP 639 弃用 |

---

## 2. 逐文件发现

### P1（必须修，影响回归可信度）

#### P1-1 `tools/verify_install.py` + `tests/test_packaging.py`：HTTP 端到端冒烟可被静默跳过，`9 passed` 不构成 E2E 证据
- **证据（文件:行）**
  - `tools/verify_install.py:104-116`：
    ```python
    try:
        from fastapi.testclient import TestClient
        ...
    except ImportError:
        print("[SKIP] 未安装 fastapi/httpx，跳过 HTTP 冒烟")
    except Exception as exc:
        check(False, "HTTP 冒烟", ...)
    ```
    `except ImportError` 分支只打印 SKIP、**不写入 `FAILURES`**，随后 `:119-123` 只要 `FAILURES` 为空就 `return 0` 并打印 `结果：全部通过`。
  - `tests/test_packaging.py:135-143` 只断言 `returncode == 0` 且 `"结果：全部通过" in stdout`，**不校验 HTTP 断言是否真的执行过**。
  - `pyproject.toml:43-44` 的 `dev` extra 只有 `pytest`、`build`，**没有 `httpx`**，而 `httpx` 是 `fastapi.testclient` 的硬依赖 → 在“按声明正确安装 `.[dev]`”的环境里也可能走到 SKIP。
- **影响**：本提交最核心的 P4-2 验收（③「干净 venv 安装后 `GET /` = 200」）在最坏情况下**从未执行而测试全绿**；CI 会给出安全的假象。实测（§3 CE9）在 httpx 损坏时 `pytest tests/test_packaging.py` 输出 **`9 passed`**，同时子进程打印 `[SKIP] 未安装 fastapi/httpx，跳过 HTTP 冒烟`。
- **建议**：① `httpx` 加入 `[project.optional-dependencies] dev`；② `verify_install.py` 把“无法执行 HTTP 冒烟”计为失败（`check(False, ...)`）或引入 `--require-http` 语义与显式 `[SKIP]` + 退出码 2；③ 测试增加断言，要求 stdout 含 `GET / 返回 200` 与 `GET /static/css/style.css 返回 200` 两条 PASS。

#### P1-2 `tests/test_packaging.py:97` 的构建把 `build/`、`*.egg-info/` 写进仓库根
- **证据**
  - `tests/test_packaging.py:97`：`_run([sys.executable, "-m", "build", "--wheel", "--outdir", str(out_dir), str(REPO_ROOT)])` —— `--outdir` 只重定向**最终 wheel**，setuptools 仍以 `REPO_ROOT` 为源码目录，在 `REPO_ROOT` 内生成 `build/`（并刷新 `family_abm.egg-info/`）。
  - 我在 TEMP 副本 `...\niche_audit\after` 跑一次 `pytest tests/` 后，该副本根目录新增 `build/` 与 `family_abm.egg-info/`（`Get-ChildItem ... -Force` 输出证实）。
  - 活动仓库：`build` CreationTime `2026/10/3 13:52:50`、`family_abm.egg-info` LastWriteTime `2026/10/3 13:52:50`，提交时间 `Sat Oct 3 13:53:26 2026 +0800` → 时间上正是提交者运行测试留下。
  - 本仓库自己的验收约束：`audits/remediation_plan.md:292`「测试**不得**…写仓库内的非 temp 路径」。
- **影响**：绿测即污染仓库；`.gitignore` 虽覆盖（`git status --short` 为空），但会把陈旧 `build/lib` 与过期 `SOURCES.txt` 留给后续 `python -m build`/`pip wheel`（本仓库历史上已出现 “审查中已见 SOURCES.txt 过期”，见 `remediation_plan.md:171`），并污染限时审计/CI 缓存。
- **建议**：在 `tmp_path_factory` 内 `shutil.copytree(REPO_ROOT, dst, ignore=...)`（排除 `.git`/`build`/`*.egg-info`）后对副本构建；或改用 `python -m build --outdir ... --no-isolation` + 显式 `--build-base`（注意 setuptools 仍会写 egg-info，最稳妥仍是复制）。

#### P1-3（P2 级但同源）`requires-python >= 3.9` 与测试套件的 Python 门槛不一致
- **证据**：`pyproject.toml:10` `requires-python = ">=3.9"`；`:18-19` 声明 3.9/3.10 分类器；`tests/test_packaging.py:14` 顶层 `import tomllib`（`tomllib` 自 **Python 3.11** 起才进入标准库，PEP 680），而同文件 `:29` 直接使用；`pyproject.toml:44` 的 `dev` extra 无 `tomli` 回退。
- **影响**：在声明支持的 3.9/3.10 上 `pytest tests/` 会在**收集阶段** `ModuleNotFoundError: No module named 'tomllib'` 直接失败；而 `remediation_plan.md:300` 计划中的 CI 矩阵正是 `3.9/3.12/3.14`（且 `.github/` 在 `0b1652e` 中不存在，无任何 CI 强制执行）。包本体兼容 3.9：我用 `ast.parse(feature_version=(3,9))` 检查提交树 60 个 `.py` 文件，**3.9 语法失败 = NONE**。
- **建议**：`dev` extra 增加 `tomli; python_version < "3.11"` 并 `try: import tomllib except ModuleNotFoundError: import tomli as tomllib`；或把 `requires-python` 提到 `>=3.11`。

### P2（应在阶段 B 开始前修）

#### P2-1 基线快照未入库，且默认输出路径未忽略 → `--check` 开箱即失效，脚本按文档运行会污染仓库
- **证据**
  - `tools/baseline.py:100-102`：无 `--out/--check` 时默认写 `Path("baseline/default_seed42.json")`（相对 CWD，即仓库根）。
  - `git ls-tree -r --name-only 0b1652e | grep '^baseline/'` → **空**：提交里没有任何基线 JSON。
  - 实测 `python -X utf8 tools/baseline.py --check baseline/default_seed42.json` → `[FAIL] 基线文件不存在：baseline\default_seed42.json`，`CHECK_MISSING_EXIT=1`。
  - `.gitignore` 本次只加了 `*.whl`、`*.tar.gz`（diff `+*.whl +*.tar.gz`），**没有 `baseline/`**；而 `remediation_plan.md:300`（P8-3）明确要求把 `baseline/` 加入 `.gitignore`。
- **影响**：`baseline.py` 的核心用法 `--check 与既有基线对比并在不一致时退出码 1`（提交信息原文）在干净检出上无法执行；按 `:10` 文档示例运行会生成未跟踪文件，既是污染源也可能被误提交（`tests/test_packaging.py:76` 还专门检查 `baseline/__init__.py`，说明作者预期该目录会存在）。
- **建议**：提交 `baseline/default_seed42.json`（或 `baseline/fixture_<hash>.json`，与计划口径一致）作为受版本控制的锚点；同时 `.gitignore` 加入 `baseline/`（若选择只在测试内使用 tmp 路径则改为把默认 `--out` 指向 `tmp` 并在文档中写明）。

#### P2-2 `license = { text = "MIT" }` 与仓库实际不一致，且为已弃用写法
- **证据**：`pyproject.toml:11`；`Test-Path LICENSE` = `False`；`Test-Path LICENSE.txt` = `False`；`git ls-files | Select-String 'LICENSE|COPYING|NOTICE'` = 空；README 无 License 章节。构建时 stderr：
  `SetuptoolsDeprecationWarning: `project.license` as a TOML table is deprecated … By 2027-Feb-18, you need to update your project and remove deprecated calls or your builds will no longer be supported.`
- **影响**：分发包（METADATA `License: MIT`）对使用者做出了仓库未提供的法律授权声明；同时该写法有 2027-02-18 的硬性弃用期限，届时构建会失败。
- **建议**：新增 `LICENSE`（MIT 全文）+ `[project] license = "MIT"`、`license-files = ["LICENSE"]`（PEP 639）；README 补 License 章节。

#### P2-3 版本号被静默提升，且计划中的验收命令无法执行
- **证据**：`89081fd:setup.py:5` 为 `version="0.1.0"`，`pyproject.toml:7` 改为 `0.2.0`；提交信息未提及版本变更。实测 `import family_abm; family_abm.__version__` → `AttributeError: module 'family_abm' has no attribute '__version__'`（在 wheel 安装副本与 venv 中均如此），而 `audits/remediation_plan.md:165` 的 P4-1 验收原文正是 `python -c "import family_abm; print(family_abm.__version__)"`。
- **影响**：P4-1 的书面验收条件不成立（“部分完成”）；wheel/`family_abm.web.app` 的 `version='0.2.0'`、pyproject `0.2.0` 与包内无版本三者之间没有任何测试约束，容易漂移。
- **建议**：`family_abm/__init__.py` 增加 `__version__ = "0.2.0"`，并加一条断言 `importlib.metadata.version("family_abm") == family_abm.__version__`；在 CHANGELOG/提交信息中记录 0.1.0→0.2.0。

#### P2-4 `setup.py` 薄壳：冲突不是报错而是静默忽略
- **证据**：把 `setup.py` 改为 `setup(install_requires=["numpy>=9.9.9"], packages=["family_abm", "tests"])` 后 `python -m build --wheel --no-isolation` → `BUILD_EXIT=0`，构建日志中**除 license 弃用警告外没有任何冲突/覆盖告警**；产物 wheel `41675 B / 33 entries`、无 `tests/` 条目，METADATA 仍为 pyproject 的 9 条 `Requires-Dist`。`setup.py:4` 的注释警告“请勿在此重新声明 install_requires / packages，否则会与 pyproject.toml 产生分歧”实际上**不会被工具链执行**。
- **影响**：单一真源在结果上成立（pyproject 胜出），但写法上仍是双入口；未来协作者在 `setup.py` 里加依赖将**无任何反馈地失效**（比报错更危险）。
- **建议**：直接删除 `setup.py`（计划 `remediation_plan.md:163` 本就允许），或增加测试：断言 `setup.py` 源码中不出现 `install_requires|packages=|package_data|entry_points` 等元数据关键字。

### P3（建议改进）

| 编号 | 证据（文件:行） | 问题 | 建议 |
|---|---|---|---|
| P3-1 | `pyproject.toml:36`；`family_abm/viz/plots.py:200-203` | `networkx` 在 `plot_family_network` 内惰性导入并自带 `ImportError("... requires networkx. Run: pip install networkx")` 提示 → 对 `import family_abm` **非必需**，声明为硬依赖属过度声明（每次安装多拉一个包） | 移入 `[project.optional-dependencies] viz`（如 `viz = ["networkx>=2.6"]`），或在注释中说明“为开箱即用的可视化而声明” |
| P3-2 | `tests/test_packaging.py:24,42-50` | 依赖断言基于硬编码 9 名清单，**不与源码交叉验证**：新增 `import sklearn` 之类仍会绿；也无法发现“多余”依赖（正是 P3-1） | 用 AST 扫描 `family_abm/**` 收集顶层第三方模块名，与声明集合做双向差集断言（并维护 stdlib/自身包白名单） |
| P3-3 | `tests/test_packaging.py:76-79` | `for directory in ("tests","tools","baseline"): assert not (REPO_ROOT/directory/"__init__.py").exists()` —— `baseline/` 在提交中不存在，该断言**真空成立**；同时没有任何测试断言 wheel 内**不含** `tests/`/`tools/`（我只手工验证了 33 entries 无二者） | 删除 `baseline` 项或让断言基于“存在的目录”；在 wheel 内容测试中补 `assert not any(n.startswith(("tests/","tools/")) for n in names)` |
| P3-4 | `tests/test_packaging.py:82-87` | `assert asset in joined` 仅对拼接后的 glob 字符串做子串匹配，扩展名写错（如 `web/static/**/*.txt`）同样通过 | 断言精确 glob 列表，或直接断言 wheel 内容（后者已有，作为主判据） |
| P3-5 | `tools/verify_install.py:111-112` | 只断言 `style.css` 的 HTTP 状态码；`dashboard.js` 从不经 HTTP 获取（仅存在性检查）。实测把 `style.css` 置空 → 仍 `结果：全部通过` exit 0 | 补 `len(response.content) > 0` 或关键字断言，并补一条 `GET /static/js/dashboard.js` == 200 |
| P3-6 | `tools/baseline.py:86`；`family_abm/core/scheduler.py:16-24` | 基线只覆盖 `Scheduler("sequential")` 与默认参数；`random` / `random_activation` 两条会消费 RNG 的调度路径无基线保护。另外快照从 `time=1` 开始（实测 `time_min=1, time_max=120`）——`Simulation.step()` 先 `scheduler.step` 再 `recorder.record`，故 t=0 初值缺失 | 增加 `--scheduler` 参数或多基线；t=0 缺失已由后续提交 `47fbdff`（阶段 B）修复，此处仅留档 |
| P3-7 | `tests/conftest.py:1-9` | 新增 conftest 为的是“测试无需先安装即可导入 family_abm”，但 `tests/` 内**没有任何测试 import family_abm**（打包测试全部走子进程 + `--target` 安装）→ 当前是空转脚手架；且它把源码树塞进 `sys.path`，正是本阶段要消灭的“editable 掩盖真实缺陷”模式 | 保留但补一条真正需要的源码级测试，或显式注释当前无消费者；务必确保打包类测试继续只用安装副本 |
| P3-8 | 实测 sdist：55 entries，含 `family_abm-0.2.0/tests/test_packaging.py`，但**无** `tests/conftest.py`、无 `tools/` | sdist 里的测试文件是孤立的（`tools/verify_install.py` 缺失 → `test_installed_copy_starts_web_app` 必失败）；计划要求新增 `MANIFEST.in`（`remediation_plan.md:170,173`）未做（`git ls-tree 0b1652e | grep MANIFEST` 为空）。sdist 的 Web 资源本身**已包含**（`web/templates/index.html`、`web/static/**`） | 加 `MANIFEST.in` 显式控制 sdist（`include tools/*.py`、`include tests/*.py` 或 `prune tests tools`），避免半套测试进 sdist |
| P3-9 | `.gitignore:14-15`（本次仅 `+*.whl +*.tar.gz`） | 计划 P8-3（`remediation_plan.md:300`）要求补 `baseline/`、`examples/output/`，本次未做；而本提交恰好新增了会写 `baseline/` 的脚本（见 P2-1） | 一并补齐 |
| P3-10 | `README.md:147` 起的“## 依赖”代码块仅列 8 项（无 pydantic） | 文档成为第三条依赖清单，与 `pyproject.toml` 分歧（计划 P8-2 第⑥项要求依赖清单与 pyproject 一致） | README 指向 `requirements.txt`/`pyproject.toml` 或补齐 pydantic |

---

## 3. 反证实验记录（命令 + 实测输出）

所有命令均在 `C:\Users\asus\AppData\Local\Temp\niche_audit\` 下执行；**未在仓库内构建或安装**。

### 3.1 构建 wheel 并逐项核对（V2 / V6）

```powershell
git archive --format=tar --output="$T\after.tar" 0b1652e ; tar -xf "$T\after.tar" -C "$T\after"
python -m build --wheel --outdir "$T\dist_after"  "$T\after"    # exit 0
python -m build --wheel --outdir "$T\dist_before" "$T\before"   # exit 0 (89081fd)
```
```python
# zipfile 清单（节选）
== before: family_abm-0.1.0-py3-none-any.whl   bytes=27695  entries=30
== after : family_abm-0.2.0-py3-none-any.whl   bytes=41676  entries=33
   family_abm/web/static/css/style.css     6030
   family_abm/web/static/js/dashboard.js  25289
   family_abm/web/templates/index.html     5358
   family_abm-0.2.0.dist-info/METADATA     7328
   （33 项中无任何 tests/、tools/ 前缀）
```
仓库实际前端文件数（`family_abm/**` 非 .py 清单）：`web/static/css/style.css`、`web/static/js/dashboard.js`、`web/templates/index.html` = **3**，与 wheel 内 3 项完全一致。

**工具链口径实验（V6 差异来源）**

```powershell
python -m build --wheel --no-isolation --outdir "$T\dist_after_noiso" "$T\after"
python -m pip wheel --no-deps --no-build-isolation -w "$T\dist_after_pipwheel" "$T\after"
python -m build --wheel --no-isolation --outdir "$T\dist_before_noiso" "$T\before"
```
```
dist_after            family_abm-0.2.0-py3-none-any.whl  41676 B  entries=33  Generator: setuptools (84.0.0)
dist_after_noiso      family_abm-0.2.0-py3-none-any.whl  41675 B  entries=33  Generator: setuptools (82.0.1)
dist_after_pipwheel   family_abm-0.2.0-py3-none-any.whl  41675 B  entries=33  Generator: setuptools (82.0.1)
dist_before           family_abm-0.1.0-py3-none-any.whl  27695 B  entries=30  Generator: setuptools (84.0.0)
dist_before_noiso     family_abm-0.1.0-py3-none-any.whl  27693 B  entries=30  Generator: setuptools (82.0.1)
dist_before_pipwheel  family_abm-0.1.0-py3-none-any.whl  27693 B  entries=30  Generator: setuptools (82.0.1)
```
→ 27693 与 41676 **不能同时**在同一工具链下复现；entries 30/33 两种口径一致。

**sdist（P4-2 验收②）**：`python -m build --sdist --outdir "$T\dist_sdist" "$T\after"` → `family_abm-0.2.0.tar.gz 41399 B / 55 entries`，含 `family_abm/web/templates/index.html`、`family_abm/web/static/css/style.css`、`family_abm/web/static/js/dashboard.js` ✓；含 `tests/test_packaging.py`，不含 `tests/conftest.py`、`tools/`。

### 3.2 干净 venv 安装验收（P4-2 验收③，独立复现）

```powershell
python -m venv --system-site-packages "$T\venv_accept"
& "$T\venv_accept\Scripts\python.exe" -m pip install --no-deps "$T\dist_after\family_abm-0.2.0-py3-none-any.whl"
# 在 $env:TEMP 下（不在仓库内）执行：
from family_abm.web.app import app          # OK, title = Family ABM Dashboard
c.get('/')                                  # 200, len 5568
c.get('/static/js/dashboard.js')            # 200, len 23099
family_abm path: ...\venv_accept\Lib\site-packages\family_abm\__init__.py
```

### 3.3 `verify_install.py` 反证（V3）

基线（完好安装副本）：
```
[PASS] import family_abm -> ...\inst\family_abm\__init__.py
[PASS] 包内含 web/templates/index.html ...
[PASS] GET / 返回 200  -> 实际 200
[PASS] GET /static/css/style.css 返回 200  -> 实际 200
结果：全部通过        BASE_EXIT=0
```

| 实验 | 操作（绝对路径已核对） | 结果 |
|---|---|---|
| CE1 | 删除 `ce1_notpl\family_abm\web\templates` | `[FAIL] 包内含 web/templates/index.html` + `[FAIL] HTTP 冒烟 -> TemplateNotFound: 'index.html' not found in search path: ...` → **exit 1** |
| CE2 | 删除 `ce2_nostatic\family_abm\web\static` | 2 项 FAIL + `[FAIL] from family_abm.web.app import app -> RuntimeError: Directory '...\web\static' does not exist` → **exit 1** |
| CE3 | 只删 `ce3_nojs\...\static\js\dashboard.js` | `结果：失败 1 项 -> ['包内含 web/static/js/dashboard.js']` → **exit 1** |
| CE4 | 安装**旧 wheel 0.1.0**（无资源）后运行新脚本 | 3 项资源 FAIL + `RuntimeError: Directory ... does not exist` → **exit 1**（证明该脚本能拦截 P4-2 那类缺陷） |
| CE6 | 在安装副本 `web/app.py` 末尾加 `raise RuntimeError(...)` | `[FAIL] from family_abm.web.app import app -> RuntimeError: simulated broken app import` → **exit 1**（**未被 try/except 吞掉**） |
| CE7 | `templates/index.html` 置空 | `GET / 返回 200` PASS 但 `[FAIL] GET / 渲染出 index.html 内容` → **exit 1** |
| CE8 | `static/css/style.css` 置空 | 全部 PASS → **exit 0**（内容为空检不出，P3-5） |

**CE5 / CE9 —— 假绿路径（V3 的核心反例）**

CE5 用 `PYTHONPATH` 桩让 TestClient 导入链抛**普通 `ImportError`**（`starlette/testclient.py` 只捕 `ModuleNotFoundError`，故普通 `ImportError` 逃逸）：
```powershell
Set-Content "$T\stub\httpx.py" 'raise ImportError("simulated: httpx present but broken (plain ImportError)")'
$env:PYTHONPATH = "$T\stub"
python -X utf8 "$T\after\tools\verify_install.py" "$T\inst"
```
```
[PASS] 包内含 web/static/js/dashboard.js
[PASS] from family_abm.web.app import app
[SKIP] 未安装 fastapi/httpx，跳过 HTTP 冒烟

结果：全部通过
CE5_EXIT=0            <-- 非 0?? 否：退出码 0，HTTP 断言从未执行
```

CE9 把同一故障接到 pytest 上（用 argv 条件 `sitecustomize.py` 只影响 `verify_install.py` 子进程，避免 langsmith 插件自身导入 httpx 而崩溃）：
```powershell
# stub_sc\sitecustomize.py: 当 argv 含 'verify_install' 时让 import httpx 抛普通 ImportError
$env:PYTHONPATH = "$T\stub_sc"
python -X utf8 -m pytest tests/test_packaging.py -v -p no:cacheprovider
```
```
tests/test_packaging.py::test_installed_copy_starts_web_app PASSED       [ 77%]
============================= 9 passed in 26.56s ==============================
PYTEST_EXIT=0
# 同一次运行中子进程 verify_install.py 打印了 [SKIP] 未安装 fastapi/httpx，跳过 HTTP 冒烟
```
→ **在 HTTP 端到端从未运行的情况下，`9 passed` 依然成立。**

### 3.4 `test_packaging.py` 过宽 skip（V4）

```powershell
# (a) 让 python -m build 不可用（桩打印真实的 "No module named build" 并 exit 1）
$env:PYTHONPATH = "$T\stub_build" ; python -X utf8 -m pytest tests/ -q -p no:cacheprovider -rs
```
```
....sss..                                                                [100%]
SKIPPED [1] tests\test_packaging.py:117: 环境缺少构建工具：C:\Python314\python.exe: No module named build
SKIPPED [1] tests\test_packaging.py:125: 环境缺少构建工具：...
SKIPPED [1] tests\test_packaging.py:135: 环境缺少构建工具：...
6 passed, 3 skipped in 14.86s          PYTEST_EXIT=0
```
```powershell
# (b) 让 pip install 因“坏 wheel”这种真实缺陷失败（非环境限制）
$env:PYTHONPATH = "$T\stub_pip" ; python -X utf8 -m pytest tests/ -q -p no:cacheprovider -rs
```
```
SKIPPED [1] tests\test_packaging.py:117: pip install --target 失败（可能是环境限制）：ERROR: family_abm-0.2.0-py3-none-any.whl is not a valid wheel filename / corrupt archive
6 passed, 3 skipped in 35.00s          PYTEST_EXIT=0
```
→ 3 条唯一的打包回归测试（wheel 内容 / METADATA 依赖 / 安装副本启动）可**整体静默消失**而套件保持绿色；`:113` 的措辞还把真实缺陷归因为“环境限制”。

### 3.5 基线可复现性与 uuid 影响（V5）

```powershell
foreach ($i in 1..5) { python -X utf8 "$T\after\tools\baseline.py" --out "$T\base_run$i.json" ; Get-FileHash ... }
```
```
run1..run5 exit=0 sha256=3C2D46368EDF68F1 bytes=2654
unique hashes: 1
seed7 sha256=70DFEDCB58459A77 bytes=2659
```
JSON 结构：
```
top keys: ['seed', 'steps', 'summary']
summary keys: ['agents', 'rows', 'time_max', 'time_min']
 type FamilyMember rows 600 columns ['attr_age','state_education','state_energy','state_happiness','state_health','state_income','state_stress']
 type Household    rows 240 columns ['state_cultural_level','state_housing_quality','state_neighborhood_quality','state_savings','state_social_capital','state_total_income']
```

`agent_id` 确实存在于 recorder 输出，但被快照剔除：
```
dataframe columns: ['time','agent_id','agent_type','alive','attr_name', ... ]
agent_id sample: 6ddc79e0-d3c4-43ea-8cc5-f7ea67be6db3
```
把 `uuid.uuid4` 替换为**递增**与**递减（逆字典序）**确定性 id（后者用于探测是否存在按 id 排序的隐式依赖），逐字节对比：
```
mode=asc  sha=3C2D46368EDF68F1
mode=desc sha=3C2D46368EDF68F1
realuuid  sha=3C2D46368EDF68F1
```
→ 三者完全相同：**baseline JSON 不受 uuid 影响，也不存在 id 排序依赖**（依据 `tools/baseline.py:59` 的数值列过滤 + `core/environment.py:15,28-29` 的插入序遍历）。
隐患边界：`ml/recorder.py:28` 仍在记录 `agent_id`（uuid4，`core/agent.py:13`）；一旦未来把 id（或任何字符串列）纳入快照、或引入按 id 排序/取集合的代码路径，跨进程可复现性立刻失效。

### 3.6 `setup.py` 薄壳（V7）

```
python setup.py --version   -> STDOUT: 0.2.0            EXIT=0
python setup.py --name      -> STDOUT: family_abm       EXIT=0
python -m build (sdist+wheel) -> EXIT=0  family_abm-0.2.0-py3-none-any.whl 41676 + .tar.gz 41397
python -m pip install --no-build-isolation -e .  -> EXIT=0
  导入：file: ...\v7e\family_abm\__init__.py ; version: 0.2.0 ; from family_abm.web.app import app -> OK
```
（`pip install -e .` 后已 `pip uninstall -y family_abm` 复原环境。）

### 3.7 依赖覆盖扫描（V1）

```python
# AST 扫描 family_abm/**（排除相对导入）
__future__, dataclasses, fastapi, math, matplotlib, networkx, numpy, pandas,
pathlib, pydantic, random, scipy, sys, threading, time, typing, uuid, uvicorn,
warnings, webbrowser
```
扣除 stdlib 与自身包后第三方 = `numpy, pandas, scipy, matplotlib, networkx, fastapi, uvicorn, pydantic`；`jinja2` 无直接导入但为 `web/app.py:9 Jinja2Templates` 的传递必需。逐一验证：
- 阻断 `jinja2` → `from family_abm.web.app import app` 失败（starlette 断言 jinja2 必须安装）→ **声明 jinja2 正确**；
- `networkx` 仅 `viz/plots.py:201` 函数内导入，且 `:202-203` 自带缺失提示 → **对 `import family_abm` 非必需**；
- `pydantic` 仅 `web/app.py:10` → 属 `family_abm.web` 必需，非 `import family_abm` 必需，`starlette` 不应单独声明（fastapi 传递管理版本）。

### 3.8 仓库卫生（额外检查）

```
=== FINAL git status --short ===
(空)
=== HEAD === 47fbdff feat(core,fitting): 阶段B - 记录 t=0 基线 + 拟合输入显式化
=== root artifacts + mtimes ===
build               2026/10/3 13:52:50   2026/10/3 13:52:51
family_abm.egg-info 2026/4/27 20:01:21   2026/10/3 13:52:50   (审计期间又被改写为 13:59:59)
=== ignored entries ===
!! build/  !! examples/__pycache__/  !! family_abm.egg-info/
!! family_abm/__pycache__/  ...(core/family/fitting/ml/niche/viz/web)...
=== LICENSE? False  LICENSE.txt? False
=== dist/ False   .pytest_cache False   baseline False
```
（`git status --short` 为空是因为 `.gitignore:8-10` 覆盖了 `build/`、`*.egg-info/`、`__pycache__/`，**不代表没有污染**。）

---

## 4. 未复现 / 存疑项

1. **`27693 B → 41676 B` 这一对字节数不能在同一工具链下同时复现**：27693 需 `--no-isolation`（setuptools 82.0.1），41676 需隔离构建（setuptools 84.0.0）。同口径配对为 `27693→41675` 或 `27695→41676`。差异来源已定位为 `*.dist-info/WHEEL` 的 `Generator: setuptools (x.y.z)` 与随之变化的 `RECORD`（我逐 entry 对比确认只有这两项不同）。因此判定 V6 为“关键数字各自可复现、但组合口径不一致”，差额 1 B，不影响结论方向。
2. **无法实机验证 Python 3.9/3.10 下 `tomllib` 的收集失败**（本机只有 3.14）。结论依据是标准库事实（`tomllib` 于 3.11 引入）+ `dev` extra 无 `tomli` 回退 + `.github/` 无 CI 矩阵，属**静态判定**，非实测。
3. **未做“干净 venv + 从索引安装全部 9 个依赖”的验证**：我用 `venv --system-site-packages` + `pip install --no-deps <wheel>` 隔离包本体，能证明资源路径与 `GET /`，但**未验证 9 条依赖说明符在 PyPI 上的可解析性**（例如 `pydantic>=2.0.0` 与 `fastapi>=0.100.0` 的组合边界、`numpy>=1.21.0` 在 Py3.9 上的可满足性）。
4. **阶段 B 提交 `47fbdff` 不在本次范围**：审计期间工作树上的并发改动（`simulation.py`、`fitter.py`、`web/app.py`、新增 `tests/test_simulation_and_fitting.py`）已被其提交，我未做任何评价；本报告全部结论只针对 `0b1652e` 冻结副本。
5. **`test_packaging.py:146-158` 的“两次运行逐字节相同”本身是弱判定**（只跑 2 次）；我以 5 次独立进程 + 递增/递减 uuid 替换做了加强，仍未覆盖 `Scheduler("random")` 路径（基线不用该路径）。
6. 我**未**在隔离 env 中验证 `sdist → pip install` 的完整链路（阶段 A 的验收口径是 wheel，已完成）。

---

## 5. 是否放行进入阶段 B 的结论

### 结论：**有条件放行**

**放行依据（我已独立复现，非照抄提交信息）**
- P4-2 的核心目标真实达成：wheel **41676 B / 33 entries**，`web/templates/index.html`、`web/static/css/style.css`、`web/static/js/dashboard.js` 三件资源全部在包内，仓库实际前端文件（3 个）无遗漏；`tests/`、`tools/` 未进 wheel；sdist 亦携带资源。
- P4-2 验收③在 venv 中独立通过：安装 wheel 后 `from family_abm.web.app import app` 成功，`GET /` = 200、`GET /static/js/dashboard.js` = 200。
- P4-1 依赖清单对**直接第三方导入无遗漏**，`requirements.txt` 与 pyproject 一致且有测试约束。
- P0-3 的可复现性属实：5 个独立进程同 seed 逐字节相同、不同 seed 不同；**uuid4 已被证明不影响快照**（JSON 不含 `agent_id`，替换 uuid 生成器后输出字节相同）——该隐患在本提交下被规避，但边界脆弱（见下）。
- 反证实验成立：删 `templates/`、`static/`、单个 `dashboard.js`、装旧 wheel，`verify_install.py` 均**非 0 退出且给出可读错误**。

**必须在进入阶段 B 之前（或阶段 B 首个提交内）先修的问题**
1. **P1-1（最高优先）**：消除 HTTP 冒烟假绿 —— `tools/verify_install.py:113-114` 的 SKIP 路径必须计失败；`httpx` 加入 `pyproject.toml:43-44` 的 `dev` extra；`tests/test_packaging.py:135-143` 增加“HTTP 断言确实执行过”的断言。**在修复前，`9 passed` 不能作为 P4-2 端到端验收的证据。**
2. **P1-2**：`tests/test_packaging.py:97` 改为在 `tmp_path` 复制源码树后构建，停止向仓库根写 `build/`、`family_abm.egg-info/`（当前仓库已被污染，mtime 13:52:50）。
3. **P2-1**：提交基线 JSON（或明确改为 tmp 路径）+ `.gitignore` 补 `baseline/`，否则 `--check` 这条“防回归锚点”在干净检出上不可用。
4. **P2-2 / P2-3**：补 `LICENSE` 并改用 PEP 639 的 `license = "MIT"`（当前有 2027-02-18 弃用期限）；在 `family_abm/__init__.py` 补 `__version__`，否则计划中 P4-1 的验收命令 `print(family_abm.__version__)` 不成立，且 0.1.0→0.2.0 的版本升级无记录、无测试。
5. **P1-3**：处理 `requires-python >= 3.9` 与 `tomllib` 的矛盾（`tomli` 回退或抬高下限），否则计划 P8-3 的 3.9 CI 矩阵无法落地。

**不阻塞放行、建议排期**：P2-4（删除 `setup.py` 或加关键字禁用测试）、P3-1～P3-10（`networkx` 降为 extra、依赖断言改为源码交叉验证、补 `MANIFEST.in`、README 依赖清单对齐、`verify_install.py` 补内容/dashboard.js 断言等）。

**风险提示（给 Lead）**：本提交引入的 `tools/baseline.py` 尚未入库基线文件，而阶段 B（`47fbdff`）改动 `core/simulation.py` 的 t=0 记录语义——按 P0-3 的要求，阶段 B 合入后必须先固化新基线并评审差异；否则“基线锚点”在阶段 B 之后将无参照物。
