# AGENTS.md —— NX 分层拉伸自动化（AI 接手文档）  v1.36

> 本文档写给**接手本项目的 AI**，位于 docs\ 子目录。用户手册（给人看）在同目录 `使用手册.md`。

## 1. 项目概况

| 项 | 内容 |
|---|---|
| 主脚本 | `nx_extrude_runner.py`（NX 2312 Python 期刊；DXF→3D） |
| 可移植性 | 整个 NX\ 文件夹自包含，可随意移动/拷贝（路径全相对脚本自身） |
| 生成物 | dlx/运行报告/调试脚印统一写入 `logs\`；__pycache__ 已禁生成 |
| 配置 | `nx_std_config.py`（用户手工编辑；主脚本 `_load_user_config()` 动态加载，缺文件/缺键逐项回退内置默认） |
| 标准件库 | `stdparts\*.prt`（必须与脚本同目录；v1.36 起 14 件已全部归零，定位点=零件原点） |
| 归零工具 | `tools\nx_zero_ref.py`（v1.36 新增：日记播放，逐件点定位点，自动预览/写回归零副本；细节见文件头注释） |
| 版本管理 | git 仓库（origin=github.com/xlzxld/HYT-NX，main 分支）；每次用户确认更新即 bump 小版本+commit+tag+push |
| 期刊留档 | `journals\`（**未随迁，当前不存在**；历史参考） |
| 开发目录 | `tools\`（归零工具/探针/提取）+ `test\`（回归脚本 + fixtures，根 = test 上一级） |
| 运行方式 | NX 内 工具→日记→播放；批量 `run_journal.exe 脚本 --batch`；离线自测 `--selftest`（155 项断言；总数随 config 标准件条目数浮动） |

## 2. 执行流水线（run_pipeline 阶段序）

1. 解析 DXF（LINE/ARC/CIRCLE；GBK/UTF-8 回退；非平面按 Z=0；不支持实体(LWPOLYLINE 等)计数——建模图层命中时日志警告+弹窗，不静默丢几何）；
2. 清理上一轮（四类：CAD3D_ 特征 → 已标记哑体 → 已标记曲线 → CAD3D_C_ 组件；无标记曲线按几何指纹判定是否旧版遗留）；
3. 图层映射 + 类别 + 建 NX 曲线；
4. 分层拉伸/布尔（FLB 基准体 → none → subtract）；
5. 标准件放置（组件→提升实体→删组件→按需布尔）；
6. JRT 加热条两侧直建；
7. 移除参数（体打 CAD3D 标记 → RemoveParameters → 清特征登记表）。

三段式对话框：①选件(toggle) ②分层拉伸(double+联动) ③标准件参数(每件一组)；
窗口②收集后、窗口③执行；DXF 路径在窗口② OK/应用时校验（无效弹窗不放行）。

## 3. 关键机制与定案（都是用户拍板/实物实证，勿凭感觉改回）

| 机制 | 定案 |
|---|---|
| 参考点 ref | **v1.36 起 14 个 prt 已全部归零，ref 恒为 [0,0,0]**——定位点=零件原点，放置公式精确对准锚点，坐标不再需要维护（config/json 均已清零）。自动探测链 v1.30 已删（STD_REF_POINTS/主导轴/大圆柱顶面/顶面后沿中点），**不要复活**；新件用 nx_zero_ref.py 归零或设计时原点建在插入位置 |
| config 两级匹配 | 精确文件名行(带/不带 .prt) > 关键词子串行；复合名文件必须有自己的精确行（"主进胶与中心定位垫片"含"垫片"，否则错命中 DK 规则） |
| Z 基准 | 选项表 = config `ZMODE_DEFS`（key/中文/图层/TOP-BOTTOM），加一行=新基准；`_std_z` 查表，查不到回 FLB_TOP |
| CXK | 只做接线盒定位不建模；曲线并入 CX 一起闭环（`modeling_ents`）；CXK 件参数页不显示半径框 |
| JRT 异形判据 | 齐平端倒圆后体内**残留型20 样条拔模面=异形**（jrt2.prt 六状态实物定案）→ 撤销降 R 重试至下限 → 兜底回退"出线端删面完成状态"。型23/样条墙产出的样条面**不是**异形（01.dxf 实证）；正常 G1 全长滚圆丢体约 11% |
| JRT 删面 | 锚点=出线口线中点(两邻都是线的短线)；面=半径≈R 且距锚点≤2.5R+2；删前后**型20 不增加**、碎片面(bbox 零维≥2)不得出现；违规→撤销→单片回退→全失败保留倒圆面 |
| JRT 开链 | 断口≤1mm 自动合并+桥接（桥接线打标记随重跑清理）；大缺口不桥（直线桥会包怪条）——跳过+日志报断口坐标 |
| 防卡死护栏 | 单件锚点>STD_MAX_ANCHORS 或"空图层+半径上限≥999"指纹 → 跳过+提示 |
| 移除参数 | 用户定案"执行后只要实体"：产物体打标记→RemoveParameters；失败留特征树不影响产物 |
| 配置健壮性(v1.35) | config 顶层标量经 `_cfg_num/_cfg_int` 归一化(拒 nan/inf/坏类型, 非法回默认不崩)；`_load_user_config` 失败/字段异常记入 `_CFG_NOTES`(去重队列)——启动弹窗+流水线日志+自测三通道输出, **不再静默回退**；ZMODE_DEFS 缺键/坏行兜底内置三行 |
| 记忆安全(v1.35) | `params` 受 schema 门控(v1.35 起调大 CONFIG_SCHEMA_VERSION=界面参数+规则记忆一并回默认, 文档口径已兑现；现值 4, 旧 schema=3 记忆已在升级时重置一次)；坏 JSON 改名 `.bad-<时间戳>` 隔离防覆盖；save_state 临时文件+os.replace 原子写 |
| -Z 放置公式(v1.35) | `pos=锚点−R·ref+off`(`_place_delta` 纯函数)：翻转件 ref 的 y/z 随姿态反号——直接用 −ref 会错位 2·ref_yz |
| 链环判据(v1.35) | find_chains 3×3 邻桶搜索(量化格边界断口不再漏配)+T 形三叉按方向延续选段；organize_loops 重复描线环去重(否则被误判为孔)+8 顶点投票包含判定——v1.29"最小包含环"定案不变 |
| CXK 切层护栏(v1.35) | 窗口③把 CXK 件切到圆心层时半径框不存在→收集侧重置 0~15 并提示核对(防旧全半径海量锚点) |
| SUBTRACT 兜底(v1.35) | 无 FLB 体可布尔或布尔未生效时**保留独立体**并记日志——不得走删体分支(否则孔没切件也没了) |
| 标准件归零(v1.36) | 14 个 prt 定位点已平移到零件原点(ref=[0,0,0])——放置公式在 ref=0 时精确等于锚点，-Z 翻转反号问题自然消失；输出件从"模型模板"复制而来(带建模应用记录, 打开直进建模)；**新件不归零就不放置可用性**——ref 恒 0, 未归零件会整体错位 |
| JT 联动(v1.37) | JT 起止随 FLB 双模式联动：普通=起点+10/终点-15，针阀=起点+15/终点-15（FLB -40/-85 → JT -30/-100 与 -25/-100）；偏移表 config `JT_LINK_MODES` 可改，模式选择记忆 json（jt_link_mode）；联动后仍可单独改，再动 FLB 按当前模式覆盖 |

## 4. 坑点清单（血泪史，逐条都有事故背书）

**NX API 类**
1. `import NXOpen` 不挂子模块——`NXOpen.BlockStyler/Features/GeometricUtilities` 必须显式 import（批量环境预加载会掩盖，交互才炸）；
2. BlockDialog 的首显钩子实名 **AddDialogShownHandler**（AddShowHandler 不存在，try/except 会静默吞掉→预填失效→NX 会话旧值回灌=记忆问题总根因）；
3. NX 按 **dlx 文件名**回灌上次显示值（RetainValue=False 拦不住）→ dlx 必须唯一文件名（毫秒戳）；固定名=旧值死灰复燃（v1.17 翻过车）；
4. 枚举块：写用 `GetProperties().SetEnum/SetEnumAsString`（`.Value=int` 在 NX2312 赋不进；SetInteger 类型不符）；读以 `ValueAsString` 为准（`.Value`/GetInteger 不可靠）；
5. `TopBlock` 在显示前是 None；块读写必须在 show 之后（首显回调里做）；
6. 预填要加 `_initializing` 守卫——程序化写 FLB 会触发 update_cb 联动，把用户单独调过的层盖掉；
7. 按钮/裸块必须包在组里，Dialog 直接子项不渲染；
8. `MassProperties`：`NewMassProperties` 要 **5 个单位对象**；`mp.Volume` 有的绑定是属性有的是方法（callable 兼容）；对非工作部件调用失败（先 SetActiveDisplay+SetWork）；
9. `Parts.Open` 已加载文件抛 "File already exists"——按路径在 session.Parts 里找回来（`_open_part` 已删，如需重建见 git/备份）；
10. `SetDisplay` 签名多态坑——用 `SetActiveDisplay(part, DisplayPartOption.AllowAdditional, PartDisplayPartWorkPartOption.UseLast)` + `SetWork`；
11. `CreateImage` 批处理不可用（无图形窗口），渲染验证走 `uf.Facet.FacetSolid(tag, params)` + `CycleFacets(model, 0)`（种子是 int 0 不是 None）导出面片离线渲染。

**几何判据类（全部实物实证，勿凭直觉推翻）**
12. 面类型（AskFaceData[0]）：16圆柱/18锥/19圆环/22平面=解析；**20=B样条**；23=样条倒圆面。平面 bbox 必有 1 个零维（法向厚度），碎片面=零维≥2；
13. 样条墙+拔模几何下倒圆产样条面属正常；正常 G1 全长滚圆丢体约 11%（阈值只能拦粗大异常：>25% 或体积≤0）；
14. 厚度理论（2R>条厚=异形）被对照实验证伪（R3.7 反产样条面而 R3.9 全解析）——用户手工流的异形源自其开口轮廓由 NX 补线，拓扑与 2D 闭链不同。

**工程流程类**
15. **NX 日志编译缓存按 路径+秒级 mtime**——同一秒改完立即跑会执行旧代码（症状：日志与最新代码行为矛盾，曾连续误导数轮）。对策：测试脚本换新文件名 / sleep 1 / 删 __pycache__。__pycache__ 的生成已在配置加载处禁用（sys.dont_write_bytecode），但对主脚本自身的 NX 缓存无效——坑仍需警惕；
16. `python - <<EOF` heredoc 写含反斜杠路径/三引号的补丁必炸——**一律用 Write 工具写补丁脚本再执行**；
17. 补丁脚本多次重放会重复追加/互相覆盖（config 曾出现 4 份重复区块）——重放前先从干净源恢复，改完 grep 计数验证；
18. 恢复/同步前确认"哪份是最新"：test 目录可能领先正式目录（用户实测时会改 test），**别用旧副本覆盖新成果**（发生过一次，靠 diff 挽救）；
19. selftest 断言与实现必须同步——删函数时同步删断言，补函数时同步补断言（v1.30 恢复曾静默丢失一批断言，掩盖问题数轮）。
20. `_undefined_name_check` 的函数内局部名表原只认 FunctionDef——函数内 `class Xxx:` 定义曾是盲区，会误报 NameError（v1.35 已补 ClassDef）；再遇自测"AST 未定义名称"误报先查这里。

**NX2312 Python 绑定类（v1.36 归零工具实证；facade 只暴露部分 .NET 面，缺就换等价路线，别硬调）**
25. `Parts.OpenBasePart`/`OpenDisplay`、`Part.CreateMoveObjectBuilder`、`UF Ui.SpecifyScreenPosition` **均不存在**（AttributeError）——打开部件走 UF `Part.Open`+`SetDisplayPart`；点定位点用 BlockStyler `UICOMP_point` 对话框（SelectionDialog 同款模式；**必须注册 AddInitializeHandler**，缺它 Launch 报"初始化回调未注册"）；部件内平移没有移动 API——改走"新建部件→组件按 −位移 放置→提升→移除参数"；
26. **AddComponent 同名循环装配**：新部件内部名与待加部件相同(仅目录不同)→"Attempt to load a cyclic assembly structure"——输出件用不同内部名(临时名)创建，Save/Close 后磁盘改名；
27. **SaveAs 到与会话中已加载部件同名的路径被拒**("File already exists")——同上，走"存临时名→关部件→os.replace"；NX 判重按部件名不按完整路径；
28. **提升体在 RemoveParameters 前关联组件壳**：删壳/隐藏壳会连带破坏/隐藏提升体（"加载完成就缺料/全消失"两案）——提升后**立即移除参数**成哑实体再动壳；
29. **关窗口≠关部件**：工具用过的部件残留会话+未保存更改，退出 NX 全冒出来——预览放工具自建临时部件，用完即弃（CloseModified=丢弃）；写回后关闭源部件（归零件与原件同名，原件不关则打开副本报"已加载另一版本的部件"）；
30. UF 分组 `Group.CreateGroup` 参数形态对不上（"函数采用 N 个参数"即此类绑定面不齐）——标识改用体名，别恋战；
31. 输出件要"打开直进建模"：从 `UGII	emplates\model-plain-1-mm-template.prt` 复制为基底（模板自带 UG_APP_MODELING 记录）；空白 UF_PART_new 件停在基本环境，ApplicationSwitchImmediate 不可用；二进制验证法：`grep -ac UG_APP_MODELING 文件`（原件 2 处）。

**向下兼容（NX10/12）类（实机探针 v2.1/v2.2 定案，勿凭 2312 经验改回）**
21. NX10/12 的 `NXOpen.pyd` 是 **Siemens 自研 CPython C 扩展绑定，不是 pythonnet**——无 `System` 模块、对象无 `GetType()`/反射、无 `.array()`。跨版本差异表现为"同一代码新绑定能编组、旧绑定报 `没有过载与这些参数匹配`"；**造 .NET 数组 / 反射签名两条路在这两版物理不可用**，定位只能读方法 `__doc__` + 逐参数试形态。
22. `Section.AddToSection`：旧版 seed/两 connector **不接受裸 `None`**，要 `NXOpen.NXObject.Null`（2312 才自动转）。已封 `_add_to_section_compat`（主脚本 L2176）——先 None(2312 零回归)后 Null 重试。注意 `rules` 用 Python list、`helpPoint` 用 Point3d、`Mode.Create` 枚举、7 参 各版皆可，**别误改这几处**。
23. `ScRuleFactory.CreateRuleOptions` **NX10/12 不存在**（AttributeError），旧版 `CreateRuleFaceDumb/CreateRuleOuterEdgesOfFaces` 只有单参重载。已封 `_sc_rule_options`（L2200）取不到返 None，EdgeBlend(L2945)/DeleteFace(L3153) 据此降级；EdgeBlend 5 核心属性(L2963)已逐条 try 防旧版缺属性崩整条。
24. NX10=Python 3.3.2 缺 `importlib.util.spec_from_file_location` → 配置加载已改三级梯 `_import_module_from_path`(L365：importlib→imp.load_source→exec)；`ast.AsyncFunctionDef` 仅 `--selftest` 触发，期刊不跑故未动。dlx(含 2312 戳)/数组参数/布尔5参/AddComponent6参 实测旧版均可用，**无需加版本分支**。

## 5. 修改流程（铁律）

1. 改动直接针对本目录的主脚本/config（v1.34 起只有一份文件；改前提醒用户手动备份）。回归套件在 `dev\.zcode\`（自相对路径+自带 fixtures\，整个 NX\ 移走后照样能跑）；
2. `python -m py_compile` + `--selftest` 全绿（现 155 项；总数随 config `STD_PART_DEFAULTS` 条目数浮动）；
3. NX 批量回归：`test\test_batch111.py`（3Dtest 全家族两遍）+ `test\test01x.py`（01.dxf 加热条）+ 可选 test123/test_ref；
4. **用户实测通过**后再移动同步到本目录（用户曾明确要求此流程）；
5. 文档同步更新（使用手册 + 本文件）；
6. **git 收尾（v1.36 起）**：用户确认更新后 bump 小版本（一直 1.x，大版本由用户临时定）→ `python -m py_compile` + `--selftest` 全绿 → `git add -A && git commit && git tag v1.x && git push --tags`。

## 6. 配置项一览（nx_std_config.py，细节见其内置注释）

| 项 | 内容 |
|---|---|
| `CONFIG_SCHEMA_VERSION` | 记忆版本守卫（加大=丢弃旧规则记忆**与界面参数**；现为 4，v1.35 已重置一次旧记忆） |
| `STD_PART_DEFAULTS` | 标准件规则表（两级匹配；ref 已全部归零为 [0,0,0]，勿再填实测值） |
| `ZMODE_DEFS` | Z 基准模式表（可自行新增基准） |
| `JT_LINK_MODES` / `JT_LINK_DEFAULT` | JT 联动偏移表（普通模式 +10/-15、针阀模式 +15/-15）与默认模式（普通模式） |
| `LINK_OFFSETS` | 分层联动偏移（RZ+13/DK-3/DP+6.7023） |
| `JRT_INTRUSION_DEFAULT` | 加热条入侵深度默认 7.5 |
| `JRT_OFFSET/JRT_DRAFT` | 壁偏置 5.0/拔模 2.0 |
| `JRT_COLOR_STRIP/MODEL/TRANSLUCENCY` | 186/78/50 |
| `NX_LAYER_START/JRT/DYNAMIC_START/MAX` | 图层分配 11/18/19/70 |
| `LAYER_START_DEFAULTS` | 各层初始拉伸距离（全新记忆时的占位值） |
| `STD_MAX_ANCHORS` | 单件放置数护栏 200 |
| `JRT_BLEND_R/R_STEP/R_MIN_DEFAULT` | 3.9/0.1/3.7（永不进记忆） |

## 7. 版本历史（详见主脚本文件头；此处仅骨架）

v1.35 全面代码审计修复（高1/中16/低15+休眠段清理；DXF 不支持实体不再静默丢、-Z 放置公式、config/记忆健壮化、链环判据加固、schema 3→4；详见主脚本文件头 v1.35 条目与审计报告） · v1.36 标准件全面归零（ref 恒 [0,0,0]，config/json 已清零）+ 新增归零工具 + git 版本管理启用（首次推送 github xlzxld/HYT-NX） · v1.37 JT 联动双模式（普通/针阀；窗口②"JT 联动模式"下拉 + 记忆 jt_link_mode；偏移表 config JT_LINK_MODES 可改）+ 目录重组（dev → tools + test）。

**NX10/12 向下兼容改造（进行中，暂未 bump 版本号，待端到端 `--batch` 通过后定）**：主脚本新增 `_add_to_section_compat`/`_sc_rule_options`/`_import_module_from_path` 三兼容助手 + EdgeBlend 逐属性守卫（详见 §4 第 21~24 条与 `docs\NX10-12兼容性评估报告.md` v2.0）；`--selftest` 全绿；探针 `probe_nx_compat.py` 迭代至 v2.2。

## 8. 用户工作偏好（遵守）

- 中文交流；计划要详细，拿不准就问；
- **不做自动备份**（用户手动备份），直接改；
- 文档只在用户要求时更新；
- 改动先在 `test\` 验证，用户实测通过再动正式目录；
- 每次用户确认更新后：bump 小版本 + git commit/tag/push（用户 2026-09 指定；大版本升级由用户临时决定）。
