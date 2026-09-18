# HYT-NX

> Siemens NX 二次开发：AutoCAD 2D 图纸（DWG / DXF）一键转 3D 热流道分流板、孔系布尔、标准件装配与 JRT 加热条闭环建模。
>
> **支持环境**：Siemens NX 10 / NX 12 / NX 2312 及以上（Python 3.3 ~ 3.12+）
> **当前版本**：v2.13（CAD3D 流水线）/ v1.4（模具自动开框）/ v3.2（一键替换标准件）

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

1. **分层拉伸与布尔切割**：自动识别 FLB 基准轮廓，按图层联动距离拉伸实体并从分流板精准布尔减去。v2.13 起 `RZ`（热咀孔）/`DK`（点孔）默认 `0/0`（= 不做）并解除与 FLB 的联动——热咀的让位孔改由热咀标准件按"放置+减去"自己挖。
2. **标准件自动装配**：扫描 `stdparts/` 库中的 `.prt`，根据图纸圆心锚点计算三维位移与姿态，完成 AddComponent + 实体提升 + 切槽/合体。热咀族（大水口/点胶口/热咀/nozzle）布尔方式默认**放置+减去**（v2.13）。
3. **JRT 加热条闭环建模**：支持 ≤1mm 细小断口自适应桥接、嵌入端倒圆、出线口删除面愈合、双侧镜像与独立着色；删面位置（出线口）优先按 `JRTFBX` 标记图层定位，图纸上没有标记时自动按条轮廓辨认。v2.12 起另加三道保险：导轨线画过头压回长线的重复短描线自动剔除（不再把闭链拆散导致整根条漏做）、齐平端起试 R 按条高收小（避免与嵌入端圆角碰头被 NX 裁成缝）、倒圆"空转"（体积几乎没变）判失败并降 R 重试。
4. **无参数化归整**：建模完成后自动 Remove Parameters，清空特征树依赖，仅保留纯净几何哑实体。
5. **增量清理与无损重跑**：每次重放自动清理上一轮生成的特征、体、组件与曲线，不影响用户自绘图形。
6. **模具自动开框**：`nx_mold_cut_runner.py` 独立入口，支持试切与冲突保护，重跑安全。
7. **一键替换标准件**：`nx_std_replace_runner.py` 独立入口，指定"把哪些换成哪些"后原位替换；定位靠反推锚点（默认不读图纸），未指定的标准件保持原样。v3.2 起：两页向导**不再记任何记忆**（每次从"不替换"与出厂参数开始），且**热咀替换自动按旧件长度对齐新件长度**（头部 30mm 一段不动、**其余就地移面**——体不重建、头身不留缝）。

> 三个入口启动时都会在控制台打印【三个脚本分别是干啥的】的大白话说明（v2.13），帮你分清该播哪一个。

---

## 三、仓库结构

### 3.1 根目录核心文件

| 路径 | 属性 | 说明 |
|---|---|---|
| `nx_extrude_runner.py` | 主入口 | CAD3D 分层拉伸与装配的 NX Journal 入口门面（v2.13），日常使用请勿修改 |
| `nx_mold_cut_runner.py` | 入口 | 模具自动开框的 NX Journal 入口（v1.4） |
| `nx_std_replace_runner.py` | 入口 | 一键替换标准件的 NX Journal 入口（v3.2），只动标准件、按"旧件→新规格"映射替换，热咀自动按旧件长度**移面**对齐，两页均无记忆 |
| `nx_std_config.py` | 用户配置 | 全局工程参数与标准件规则（v2.13），业务调参改此文件。**注意：配置文件等同可执行代码**（程序以 exec 方式加载以支持跨版本 API 兼容梯与表达式配置），勿使用来历不明的配置文件，外部单位交付时建议随附校验或锁定 |
| `nx_extrude_params.json` | 运行时记忆 | 交互记忆持久化，由程序自动维护；参数错乱可直接删除重建 |
| `batch_smoke.py` | 测试入口 | NX 内端到端冒烟脚本（免命令行版） |
| `AGENTS.md` | 契约 | 项目 AI 开发契约（铁律 / 红线 / 验证门禁），所有 AI 助手唯一标准入口 |
| `.agents/AUDIT-SPEC.md` | 契约 | 审计规格，与 AGENTS.md 同批修订 |
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
| `docs/` | 文档 | 使用手册、验收手册；本地《移植手册》不入库 |
| `.agents/enforcement/` | 脚手架 | pre-commit / commitlint / CI 工作流模板（见 `.agents/enforcement/README.md`） |

---

## 四、快速上手（在 NX 内运行）

### 4.1 标准三段式交互（CAD3D 主流程）

1. 启动 Siemens NX，新建或打开毫米建模部件；
2. 菜单 **【工具】(Tools) → 【日记】(Journal) → 【播放】(Play)**，选择 `nx_extrude_runner.py`（控制台先打印三个脚本各自作用的大白话说明）；
3. **窗口①**：标准件装配清单勾选（自动记忆上次选择，新零件默认不勾）；
4. **窗口②**：图纸路径 + 分层拉伸尺寸 + JRT 加热条主参数（修改 FLB 时联动层 LS/DP/JRT/JT/CX 按工程预设跟随；`RZ`/`DK` v2.13 起默认 `0/0` = 不做、不随 FLB 联动，需要时自行填数）；
5. **窗口③**：各标准件参数微调（定位图层 / Z 基准 / X/Y/Z 偏移 / 布尔模式；热咀族布尔默认**放置+减去**），确认后开始全自动建模；
6. 控制台逐行打印建模步骤，结束生成 `logs/nx_extrude_report.txt`。

> **图纸格式**：v2.2 起直接支持 `.dwg`，系统会在后台静默转换为标准 DXF；首次转换结果存到 `logs/_dwg_cache_*.dxf` 复用（同图第二次免转换，图纸改动或大小变化自动重转），过程中不再产生临时残留。

### 4.2 模具自动开框（开框流程）

1. 先用 `nx_extrude_runner.py` 跑完分层拉伸流水线；
2. 把模具手动放入当前工作部件并摆好位置；
3. 播放 `nx_mold_cut_runner.py`（默认 `MODE = "cut"`）；切换为 `MODE = "api"` 可只读探测本 NX 可用 API 写到 `logs/mold_api_probe.txt`；
4. 控制台末行 + `logs/mold_cut_report.txt` 给出 `MOLD RESULT ok=True tools=N mold=M cuts=K skip=S fail=F conflict=C`。

---

### 4.3 一键替换标准件（换规格）

1. 先用 `nx_extrude_runner.py` 把标准件放好；
2. 播放 `nx_std_replace_runner.py`（控制台先打印三个脚本各自作用的大白话说明）；
3. 窗口①列出模型里**现有的**标准件，逐个在右侧挑"换成哪个规格"；留在"不替换"上的整件不动（**不记上次的选择**，每次都从"不替换"现选，v3.1）；
4. 窗口②逐件微调参数（**参数不读记忆**，恒从 `nx_std_config.py` 出厂默认开始），Apply/OK 执行；
5. 控制台末行 + `logs/std_replace_report.txt` 给出 `REPLACE RESULT ok=True pairs=N old=X new=Y skip=S adj=A`（`adj` = 热咀长度对齐成功的处数）。

定位靠**主脚本记在体上的锚点**：放置时把「锚点 − 该体包围盒中心」和放置角写进体属性 `CAD3D_ANCHOR_OFF`，替换时直接 `当前锚点 = 当前体中心 + 偏移`。记偏移不记绝对坐标 ⇒ 你手动把标准件挪到别处，反推出来的锚点会**跟着走**；同件的多个体各算一次必须重合，这既是归组依据（一个实例只放一个新件）也是正确性自检。**全程不读图纸。**

**热咀长度自动对齐（v3.2）**：替换热咀族（大水口/点胶口/热咀/nozzle，关键词可在 `nx_std_config.py` 的 `NOZZLE_FAMILIES` 配置）时，新件放好后自动把总长对齐旧件（旧件长度 = 旧件标准件体的顶部到底部）：头部（顶部往下 `NOZZLE_KEEP_HEAD`，默认 30mm）不动，**这一带以下的面用同步建模「移动面」就地平移**差值——比旧件短就拉长、比旧件长就缩短，与手动"移动面"选面做法同口径。体不重建，所以头与身之间不会留缝；头身同体时该体被拉伸、分开时下面几块整体随动。移面后脚本会复测总长并回填日志。

**图纸无 DK 图层时的垫片兜底（v3.2）**：主脚本在窗口③会临时把靠 DK 定位的件（`垫片.prt`）的定位图层与半径换成热咀那套（层 `RZ`），让它照样能放上；**Z 基准与布尔方式仍是垫片自己的**，且这个临时改动**不写进记忆**——换回带 DK 的图纸会自动恢复原参数。

⚠️ 体上没有锚点记录（老版主脚本建的模型）会报「无标准件锚点」并原样不动 —— 重跑一次主脚本就会补上。

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

门禁命令定义在 `Makefile`，与 `AGENTS.md` §2 登记保持一致。lint 走 ruff，存量 321 条历史豁免条目（F401 / I001 等 NX10/12 旧版 Python 风格）按增量仅查本次改动文件，**新增代码必须 0 问题**。test 走 `--selftest`（当前 336 项断言全绿）。

> 主干保护（`main`）强制 PR 合入 + `gate` CI 必须通过，**禁止未经 PR 直接 push 主干**（见 `AGENTS.md` §2 与 `enforcement/gate.yml`）。

---

## 七、文档导航

| 文档 | 用途 |
|---|---|
| [`docs/使用手册.md`](docs/使用手册.md) | CAD3D 主流程的标准三段式操作 + 图纸规范 + 参数配置 |
| [`docs/验收手册.md`](docs/验收手册.md) | 验收测试用例与判定标准 |
| [`AGENTS.md`](AGENTS.md) | AI 开发契约（铁律 / 红线 / 行为契约 / 验证门禁）—— 所有 AI 助手唯一标准入口 |
| [`.agents/AUDIT-SPEC.md`](.agents/AUDIT-SPEC.md) | 审计规格（与 AGENTS.md 同批修订） |
| [`.agents/enforcement/README.md`](.agents/enforcement/README.md) | 执法脚手架四步安装与日常使用 |
| [`tools/`](tools/) | NX 向下兼容工具与标准件归零工具的源码与说明 |

> 老旧机器移植（NX2312 开发机 → NX 10/12）见本地《移植手册》`docs\移植手册.md` ——
> 该文件不入版本库，随移植包单独交付。

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