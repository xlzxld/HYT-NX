# HYT-NX

> Siemens NX 二次开发：AutoCAD 2D 图纸（DWG / DXF）一键转 3D 热流道分流板、孔系布尔、标准件装配与 JRT 加热条闭环建模。
>
> **支持环境**：Siemens NX 10 / NX 12 / NX 2312 及以上（Python 3.3 ~ 3.12+）
> **当前版本**：v2.11（CAD3D 流水线）/ v1.3（模具自动开框）

---

## 一、项目定位

本仓库是一套面向热流道模具设计的 Siemens NX Journal 自动化脚本集，代号 **CAD3D**。所有功能通过 NX 菜单 **【工具】→【日记】→【播放】** 启动，按图纸自动完成"线框 → 实体 → 装配 → 开框"的全流程，避免手工建模的低效与误差。

主要适用对象：

- 热流道分流板（FLB）、假体（JT）、出线槽（CX）、孔系（LS / RZ / DK / DP）的分层拉伸与布尔切割
- 热咀、螺丝、垫片、接线盒等标准件的自动装配与特征切割
- JRT 加热条的闭环建模（嵌入端倒圆、出线口愈合、切槽、圆顶倒圆、双侧镜像）
- 已建好模型的模具自动开框（含可选试切与冲突保护）

---

## 二、核心能力

1. **分层拉伸与布尔切割**：自动识别 FLB 基准轮廓，按图层联动距离拉伸实体并从分流板精准布尔减去。
2. **标准件自动装配**：扫描 `stdparts/` 库中的 `.prt`，根据图纸圆心锚点计算三维位移与姿态，完成 AddComponent + 实体提升 + 切槽/合体。
3. **JRT 加热条闭环建模**：支持 ≤1mm 细小断口自适应桥接、嵌入端倒圆、出线口删除面愈合、双侧镜像与独立着色；删面位置（出线口）优先按 `JRTFBX` 标记图层定位，图纸上没有标记时自动按条轮廓辨认。
4. **无参数化归整**：建模完成后自动 Remove Parameters，清空特征树依赖，仅保留纯净几何哑实体。
5. **增量清理与无损重跑**：每次重放自动清理上一轮生成的特征、体、组件与曲线，不影响用户自绘图形。
6. **模具自动开框**：`nx_mold_cut_runner.py` 独立入口，支持试切与冲突保护，重跑安全。

---

## 三、仓库结构

### 3.1 根目录核心文件

| 路径 | 属性 | 说明 |
|---|---|---|
| `nx_extrude_runner.py` | 主入口 | CAD3D 分层拉伸与装配的 NX Journal 入口门面（v2.11），日常使用请勿修改 |
| `nx_mold_cut_runner.py` | 入口 | 模具自动开框的 NX Journal 入口（v1.3） |
| `nx_std_config.py` | 用户配置 | 全局工程参数与标准件规则（v2.11），业务调参改此文件 |
| `nx_extrude_params.json` | 运行时记忆 | 交互记忆持久化，由程序自动维护；参数错乱可直接删除重建 |
| `batch_smoke.py` | 测试入口 | NX 内端到端冒烟脚本（免命令行版） |
| `AGENTS.md` | 契约 | 项目 AI 开发契约（铁律 / 红线 / 验证门禁），所有 AI 助手唯一标准入口 |
| `AUDIT-SPEC.md` | 契约 | 审计规格，与 AGENTS.md 同批修订 |
| `Makefile` | 门禁 | `make verify` 聚合门禁（fmt-check / lint / test / build） |
| `ruff.toml` | 门禁 | Ruff 检查配置（NX 旧版 Python 风格豁免） |
| `commitlint.config.js` | 提交规范 | Conventional Commits 提交信息校验 |
| `.pre-commit-config.yaml` | 钩子 | pre-commit 入口（gitleaks + commitlint） |

### 3.2 核心代码包 `cad3d/`

| 子包 | 职责 |
|---|---|
| `cad3d.core` | 常量、路径、配置 schema、状态记忆、日志门面 |
| `cad3d.geom` | DXF/DWG 解析、实体几何、拓扑运算、几何求值 |
| `cad3d.modeling` | NXOpen 建模（拉伸 / 切除 / 倒圆 / 标准件 / JRT / 模具开框 / 兼容层 / 清理） |
| `cad3d.pipeline` | 单次流水线编排与批量入口 |
| `cad3d.ui` | BlockStyler XML 对话框定义（动态生成 dlx） |
| `cad3d.selftest` | 离线自测套件与合成样例 DXF |

### 3.3 资源与产出目录

| 路径 | 性质 | 说明 |
|---|---|---|
| `stdparts/` | 资源 | 标准件 `.prt` 库（14 个零件） |
| `test/fixtures/` | 资源 | 回归测试图纸（`3Dtest.dxf`、`sample_layers.dxf` 等） |
| `tools/` | 工具 | `nx_zero_ref.py`（标准件归零工具）、`probe_nx_compat.py`（NX 版本兼容性探测）、`probe_jrtfbx.py`（JRTFBX 标记层离线体检，不依赖 NX）、`NX向下兼容工具/` |
| `logs/` | 产出 | 运行生成的 `.dlx` / 报告 / 调试日志；可随时删除，下次运行自动重建 |
| `docs/` | 文档 | 使用手册、验收手册、NX10-12 兼容性评估报告、AGENTS.md 副本 |
| `enforcement/` | 脚手架 | pre-commit / commitlint / CI 工作流模板（见 `enforcement/README.md`） |

---

## 四、快速上手（在 NX 内运行）

### 4.1 标准三段式交互（CAD3D 主流程）

1. 启动 Siemens NX，新建或打开毫米建模部件；
2. 菜单 **【工具】(Tools) → 【日记】(Journal) → 【播放】(Play)**，选择 `nx_extrude_runner.py`；
3. **窗口①**：标准件装配清单勾选（自动记忆上次选择，新零件默认不勾）；
4. **窗口②**：图纸路径 + 分层拉伸尺寸 + JRT 加热条主参数（修改 FLB 时其余各层按工程预设联动跟随）；
5. **窗口③**：各标准件参数微调（定位图层 / Z 基准 / X/Y/Z 偏移 / 布尔模式），确认后开始全自动建模；
6. 控制台逐行打印建模步骤，结束生成 `logs/nx_extrude_report.txt`。

> **图纸格式**：v2.2 起直接支持 `.dwg`，系统会在后台静默转换为标准 DXF；首次转换结果存到 `logs/_dwg_cache_*.dxf` 复用（同图第二次免转换，图纸改动或大小变化自动重转），过程中不再产生临时残留。

### 4.2 模具自动开框（开框流程）

1. 先用 `nx_extrude_runner.py` 跑完分层拉伸流水线；
2. 把模具手动放入当前工作部件并摆好位置；
3. 播放 `nx_mold_cut_runner.py`（默认 `MODE = "cut"`）；切换为 `MODE = "api"` 可只读探测本 NX 可用 API 写到 `logs/mold_api_probe.txt`；
4. 控制台末行 + `logs/mold_cut_report.txt` 给出 `MOLD RESULT ok=True tools=N mold=M cuts=K skip=S fail=F conflict=C`。

---

## 五、命令行与离线自测

支持在系统 Python 3.14 下离线运行（无需 NX 运行时）：

```bash
# 离线自测（无 NX 环境）
python nx_extrude_runner.py --selftest

# 批量处理一份图纸
python nx_extrude_runner.py --batch <dxf_path>

# 合成一份样例 DXF 用于测试
python nx_extrude_runner.py --make-sample-dxf test/fixtures/sample_layers.dxf
```

日志统一输出到 `logs/` 目录。

---

## 六、验证门禁

本项目以 **文档管行为，钩子兜底线**（见 `enforcement/README.md`）。AI 助手完成修改后必须执行：

```bash
# 全量门禁（fmt-check / lint / test / build）
make verify

# 增量门禁（仅检查本次改动文件，ruff 自动跳过非 .py 项）
make verify CHANGED="$(git diff --name-only)"
```

门禁命令定义在 `Makefile`，与 `AGENTS.md` §2 登记保持一致。lint 走 ruff，存量 321 条历史豁免条目（F401 / I001 等 NX10/12 旧版 Python 风格）按增量仅查本次改动文件，**新增代码必须 0 问题**。test 走 `--selftest`（当前 273 项断言全绿）。

> 主干保护（`main`）强制 PR 合入 + `gate` CI 必须通过，**禁止未经 PR 直接 push 主干**（见 `AGENTS.md` §2 与 `enforcement/gate.yml`）。

---

## 七、文档导航

| 文档 | 用途 |
|---|---|
| [`docs/使用手册.md`](docs/使用手册.md) | CAD3D 主流程的标准三段式操作 + 图纸规范 + 参数配置 |
| [`docs/验收手册.md`](docs/验收手册.md) | 验收测试用例与判定标准 |
| [`docs/NX10-12兼容性评估报告.md`](docs/NX10-12兼容性评估报告.md) | NX 10/12 与 2312 跨版本兼容差异与适配结论 |
| [`AGENTS.md`](AGENTS.md) | AI 开发契约（铁律 / 红线 / 行为契约 / 验证门禁）—— 所有 AI 助手唯一标准入口 |
| [`AUDIT-SPEC.md`](AUDIT-SPEC.md) | 审计规格（与 AGENTS.md 同批修订） |
| [`enforcement/README.md`](enforcement/README.md) | 执法脚手架四步安装与日常使用 |
| [`tools/`](tools/) | NX 向下兼容工具与标准件归零工具的源码与说明 |

---

## 八、贡献与提交流程

- **提交规范**：Conventional Commits（`feat:` `fix:` `refactor:` `perf:` `test:` `docs:` `chore:`），由 commitlint 钩子强制校验；
- **原子提交**：一次提交只做一件事；
- **PR 合入**：feature 分支开发，验证通过后走 PR 合入 `main`；CI gate 必须通过；
- **AI 助手约束**：见 `AGENTS.md`（R-0.1 未验证不交付、R-0.2 禁止臆造、R-1.2 闭环验证、R-1.4 大白话交流）。

---

## 九、许可与归属

仓库尚未声明开源许可证（LICENSE 文件未添加）；如需对外发布或商用，请先与维护者确认归属与许可条款。

GitHub: [xlzxld/HYT-NX](https://github.com/xlzxld/HYT-NX)