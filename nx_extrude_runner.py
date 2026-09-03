# -*- coding: utf-8 -*-
r"""
nx_extrude_runner.py — NX 分层拉伸自动化（CAD DXF → 3D）  v1.40  2026-09-02

v1.40: NX10/12 兼容收尾 + 显示刷新 + CX 联动修正（本次会话；配套探针 v2.3）:
      ① _set_expr: NX10/12 的 NXOpen.Expression 无 SetFormula(str)(2312 才有),
        旧版拉伸 offset/draft 因此崩、JRT 加热条全废 → 先 SetFormula(2312 零
        回归) 后 .RightHandSide=str(旧版同款); 新增写表达式处一律走 _set_expr;
      ② _dlg_show: 旧版 BlockStyler.BlockDialog 无 Launch()(报 no attribute
        Launch, 交互三段框第一步即崩) → 按存在性选 Launch/Show/ReplayDialog;
      ③ _refresh_display: 无界面批量/旧版末帧不自动重绘(标准件实体、DXF 曲线
        要用户 hide/show+图层全开才显形, 数据本无误) → run_pipeline 成功收尾
        + batch_run 双跑后各调一次(图层全开 SetObjectsVisibilityOnLayer + 逐
        体/曲线 Unblank+RedisplayObject + DoRebuilds), 交互与批量两条路径共用,
        逐步 try 兜底不影响模型/2312;
      ④ CX 联动修正: CX 结束原按 JT 结束−偏移(JT 结束随模式漂移不合理)→ 改为
        CX 结束 = CX 起始(=JT 起始)−偏移, 槽深固定; config CX_LINK_END_OFFSET
        默认 35; 默认普通模式 CX 由 -30/-135 变 -30/-65;
      ⑤ stdparts 目录回退: 去掉按版本切 stdparts_nx8 的设想(及 _nx_version_major),
        stdparts_dir() 固定读 STDPARTS_DIRNAME=stdparts; 旧版交付把 tools\
        NX向下兼容工具\ 还原的本机 .prt 直接放入 stdparts\ 覆盖同名即可;
      ⑥ 配套 probe_nx_compat.py→v2.3(API026 探 Expression 通道/stdparts 目录;
        S3 两遍二分坐实 AddToSection 用类型化 null), 新增 batch_smoke.py 无界面
        端到端冒烟; NX10/NX12 真机实测 API006/010/011/017 全绿、端到端通过。
      (①②⑤承接 1.38 的 _add_to_section_compat/_sc_rule_options/_import 三梯,
       本会话把剩余绑定层断点补齐; v1.39 工具包重组见下条, 二者随本版一并入库。)

v1.39: 标准件下放工具包重组:
      stdparts\NX8兼容_x_t + stdparts\_nx_export 两目录合并收拢, 移入
      tools\NX向下兼容工具\: export_xt.py(原 export_ps_v2.py)把 stdparts
      母版导出 Parasolid 24.0(NX8 schema) x_t, 统一入包内 xt\;
      verify_import.py 回读校验实体数; import_xt_to_prt.py(原
      import_to_nx10.py)拷到低版本机双击 一键导入.bat 还原 prt, 产出
      入包内 x_t转prt\(prt 版本=执行导入的本机 NX 版本, 旧版格式须在
      低版本机上导入); stage/tmp 暂存目录跑完自动删除; 使用说明.txt
      彻底重写; 弃用 export_ps.py(v1)与历史日志清理。导出→校验→导入
      链 NX2312 端到端实测 14/14(实体数零丢失); 低版本实机导入复验
      仍待做。文档同步: 使用手册目录表新增工具包行, NX10-12兼容性
      评估报告 v2.2 脚注。
v1.38: CX 联动 + 兜底默认: CX 起始恒=JT 起始, CX 结束=假体(JT)结束
      −CX_LINK_END_OFFSET(config 默认 35; 假体结束 -35 → CX -70);
      无记忆兜底默认改为 FLB -40/-85, 其余联动层按规则从 FLB 推导
      (普通模式 JT -30/-100, CX -30/-135)。
v1.37: JT 联动(双模式): JT 起止随 FLB 实时联动, 窗口②新增"JT 联动模式"
      下拉(普通模式/针阀模式), 选择记忆到 json(jt_link_mode):
      普通模式=起点+10/终点-15 (FLB -40/-85 → JT -30/-100);
      针阀模式=起点+15/终点-15 (FLB -40/-85 → JT -25/-100)。
      偏移表 JT_LINK_MODES 与默认模式 JT_LINK_DEFAULT 在 config 可改;
      联动后 JT 仍可单独改, 再动 FLB 会按当前模式覆盖。
v1.36: 标准件全面归零(ref 恒为 [0,0,0], 配置坐标维护终结):
      ①14 个 stdparts prt 用归零工具(nx_zero_ref.py)把定位点平移到零件
        原点(图形区点定位点→提升→移除参数→另存), 定位特征精确落在图纸
        定位点上; ②nx_std_config.py 与 json 记忆中的 ref 全部清零——
        放置公式 锚点−R·ref+off 在 ref=[0,0,0] 时精确等于锚点, -Z 翻转
        反号问题(v1.35 ④)随之消失; ③新增独立工具 nx_zero_ref.py:
        复用窗口①选择框+对话框点选定位点, 预览/写回全自动, 详见该文件
        头注释; ④git 仓库启用: 每次确认更新即提交+tag。
v1.35: 全面代码审计修复(高1/中16/低15, 详见审计报告):
      ①【高】DXF 不支持实体(LWPOLYLINE 等)不再静默丢弃——计数+日志
        +建模图层命中时弹窗; ②SUBTRACT 件无 FLB 体可布尔时保留独立体
        (原会误删); ③-Z 翻转件放置公式改 锚点−R·ref+off(ref 随姿态
        旋转, 原误差=2·ref_yz); ④config 加载失败/字段非法: 不再静默
        回退——原因入 _CFG_NOTES, 启动弹窗+流水线日志双通道; 顶层标量
        (_cfg_num/_cfg_int)与 ZMODE_DEFS 缺键全部兜底不崩; ⑤JSON 记忆:
        params 纳入 schema 门控(schema 3→4 全重置), 坏类型容错, 原子写
        (临时文件+os.replace), 坏文件改名 .bad-* 隔离防覆盖; ⑥find_chains
        邻桶搜索+T形方向延续选段, organize_loops 重复环去重+多顶点投票
        包含判定, 锚点去重 O(n) 化+护栏前置收集; ⑦窗口② Apply 后 Cancel
        现在真正中止; _find 不缓存 None; CXK 切圆心层半径重置 0~15+提示;
        dlx TEMP 回退改唯一名; update_cb 异常写调试脚印; ⑧清理: 删
        build_dlx 休眠标准件组与窗口② SP* 预填循环(签名同步), 删
        place_std_parts 二次 ref 检查/主导轴孤儿注释, 移除参数与着色
        builder 补 finally 释放, 流水线异常输出堆栈。
v1.34: 目录分类整理: dlx/运行报告/调试脚印归入脚本同级 logs 子目录
      (自动创建); 配置模块加载禁写字节码缓存(根目录不再出现
      __pycache__)。整个 NX 文件夹自包含, 可随意移动/拷贝。
v1.33:

v1.33: 工程参数+环境适配参数迁入 config(①+②, 算法容差留脚本):
      联动偏移 LINK_OFFSETS(RZ+13/DK-3/DP+6.7023)、JRT 入侵深度
      7.5/壁偏置 5.0/拔模 2.0/颜色 186/78/透明度 50、NX 图层分配
      (11~17/18/19/70)、各图层默认拉伸距离、stdparts 目录名——
      全部 config 可改, 默认值=原值行为零变化。
v1.32:

v1.32: Z 基准模式表开放到 config(ZMODE_DEFS): 每行=(key, 下拉中文名,
      参考图层, TOP/BOTTOM), 用户加一行=新增一种基准(如 JT 顶面),
      规则行 z_mode 即可引用; ZMODE_OPTS/_std_z/sanitize 全部改表
      驱动(查不到的旧值回 FLB 顶面)。补回 v1.30 恢复时丢失的
      selftest 断言(BOOL无停用/rule_usable/两级匹配等)。
v1.31:

v1.31: 标准件参数页按需显示: 定位图层=CXK(线中点锚点)的件不再
      生成 半径min/半径max 输入框(接线盒/压线板等; 半径筛选对线
      中点锚点无意义)。图层为圆心层的件照旧显示。收集侧对缺失块
      自动回落规则值, 无副作用。
v1.30:

v1.30: 标准件参考点全用户化: 删全部自动探测链; ref 必填按文件名
      填 config(不填=跳过+提示); config 两级匹配(精确文件名>
      关键词); ZMODE 删 ABS / BOOL 删 OFF; 删 测参考点.py。
v1.30: 标准件参考点全用户化(用户定案"废弃自动探测链"): ①删除全部
      探测链(STD_REF_POINTS 内部库/主导轴/大圆柱顶面/顶面后沿中点/
      NOZZLE_REF_KEYS/_open_part/测参考点.py)——参考点一律由用户在
      nx_std_config.py 按文件名精确行实测填写 ref:[x,y,z], 未填 ref 的
      件跳过不用并提示(日志+交互弹窗); ②config 匹配升级两级(精确文件
      名行>关键词行); ③存量件预填期刊/探查实测参考点(可自行校验修改);
      ④ZMODE 删 ABS / BOOL 删 OFF(停用=窗口①不勾选)。
v1.29:

v1.29: 测试版全面梳理后的定版(无新工艺, 仅修缺陷/清死代码/补护栏):
      ①【正确性】嵌套环 parent 判据修复——过去取"面积最大的包含环",
        三层嵌套(A⊃B⊃C)时 C 的父环被判成 A, depth=1 被当成 A 的第二个
        孔 → 岛的材料被错误减掉(应独立成体)。改为取"最小的包含环",
        depth(C)=2 → 独立轮廓; 四层同理(岛再带孔)。两层嵌套结果不变。
        自测补 三层/四层 两条断言。
      ②【可观测性】_pick_target 兜底取第 1 个 FLB 体时不再静默——
        多板图锚点落在板外会把孔切到别的板上, 现在日志留痕。
      ③【健壮性】selftest 不再依赖 nx_std_config.py 存在(配置按设计可选,
        缺失走内置兜底表, 过去会 AttributeError 直接崩)。
      ④【一致性】STD_REF_POINTS 英文关键词(screw/nozzle/ls-)改大小写
        不敏感匹配(与 std_part_defaults 的 lower 匹配统一);
        build_jrt 的 draft 兜底值改取 DEFAULT_JRT(原写 0.0 与默认 2.0 矛盾);
        nx_purge 返回值统一为"实际删除数"(失败路径原返回待删数)。
      ⑤【清理】删死代码 _body_healthy / _cleanup_stale_dlx(`_fresh_dlx_path`
        已按前缀清理, 该函数从未被调用)与未使用的 used_as_hole;
        修正 build_jrt 齐平端起试半径注释(v1.26 已回退厚度预防式,
        注释却仍描述已废弃行为)与 _edge_blend_end_retry 文档串里的旧函数名
        (_dome_new_faces_ok → _dome_body_ok)。
      ⑦【新能力】标准件参考点可自助配置: STD_PART_DEFAULTS 每行可写
        "ref": [x, y, z](零件坐标系里的插入基准点)。给了就作为最高优先级
        直接用(连零件都不用打开), 不写/写得非法则回内部自动探测链
        (配置参考点→顶面后沿中点→大圆柱顶面→主导轴→库值→原点)。
        ref 不进对话框、不进 JSON, 只从配置文件读; 收集侧改为以现有规则
        起底再覆盖对话框字段, 保证非对话框字段不被抹掉。自测补 5 项。
      ⑧【风格】_cluster_tips 缩进 8→4; workPart_rules → work_part_rules;
        MANAGED_MIN 取代硬编码 11; selftest 内 xml 别名 ET2/ET 统一为 ET;
        LAYER_SEL_OPTS 折行规范化; selftest 段落编号按出现顺序重排。
        自测 126 → 134 项。
v1.28: 删面健康补最后一缺口——**型20 样条面数量在删面后不得增加**
      (01_result diff 实证: 圆顶倒圆本体检干净, 型20×2 是删面愈合产生
      的样条补丁——即用户目检"仍不对"的部位)。触发→撤销→单片回退→
      全失败保留倒圆面。嵌入端合法的 2 片拔模样条面由"不增加"保护。
v1.27:

v1.27: 异形判据定案(jrt2.prt 六状态实物实证, 用户制造): 齐平端倒圆后
      体内残留 型20 样条拔模面 = 异形(C/D R3.9/3.8 各2片; 干净 E/F =0,
      且干净状态型23 更多 → 型23 不是判据, v1.25 判据作废)。判据纳入
      倒圆重试(触发→撤销降R至下限), 全部失败触发兜底=回退到出线端
      删面完成状态。删面锚点/安全包装/开链修复等 v1.24-25 机制不变。
v1.26:

v1.26: 决定性实验(exp_r: 同一检查点上 3.9/3.8/3.7/3.6 逐R对照)推翻
      两个理论: ①"2R>条厚=异形"——R3.7 反而产 型23 样条面而 R3.9 全
      解析, 厚度预防式起试半径(3.7)已回退; ②"样条面=异形"——样条墙
      几何下正常。实测 R3.9 齐平倒圆 24 新面全解析(优于用户手工 3.7
      结果), 用户手工流异形的根源=其轮廓为开口链由 NX 补线闭合(拓扑
      与 2D 闭链不同)。层3 网络保留: 体积>25%/碎片面/型23≈R 圆顶判据
      (仅在触发时降R), 齐平端从 blend_r 起试。
v1.25:

v1.25: 按期刊 journal-jrt.py 定案(用户同几何预览实测): ①圆顶(齐平端)
      倒圆异形判据=新面含 半径≈当前R 的型23样条翻卷面——R3.9/R3.8 触发
      撤销降R, R3.7 通过(与用户预览逐 R 吻合; 嵌入端不适用此判据);
      ②删面锚点改用出线口线中点(两邻都是线的短线; 期刊删除面正位于
      口线中点 x=487.5/512.5 处), 跨接线回退; ③圆顶全失败回退语义=
      嵌入端删面完成状态(用户口径)。
v1.24:

v1.24: ①面体检回退为仅碎片判据——样条倒圆面(型20/23)是样条墙+拔模
      几何的正常产物(01.dxf 实证: 该链全解析轮廓、倒圆仍产样条面),
      非解析判据会误杀全部倒圆; 翻卷仍由体积阈值兜底。②连接线识别
      泛化: 最短两条规则之外, 增加"两相邻段都是弧的短直线(≤15mm)"
      ——01.dxf 两出线口环形通道的 4 条等长 6.09 跨接线一案。
v1.23:

v1.23: 加热条两大问题定案修复(好样板 jrt1.prt 实证 48 面全解析:
      16圆柱+30圆环+4平面, 出线端=收口处两片 0.2×8 小平面; 01 坏条
      实证含 型20/型23 样条面与 3.9×0.0 退化碎片): ①面类型体检——
      非解析面/零尺寸碎片面=异形, 接入倒圆重试(体检不过=撤销降R,
      比体积阈值精确); ②删面安全包装——整组删→体检→撤销, 逐片删→
      体检→撤销, 都失败保留倒圆面(宁可端部多两片圆角不出变形条)。
v1.22:

v1.22: 移除"正负反转"按钮与"向右拖宽窗口"撑宽行(用户定案; 单列布局后
      宽度已完整显示, 反转不再需要)。恢复默认按钮(每件/加热条)保留。
v1.21:

v1.21: 宽度定案: 脚印文件实证 DialogSizing 仅 ['Allow Resize',
      'Follow Policy'] 无自适应项, 且 dlx 块模型无宽度属性——页2/页3
      全部组改单列布局(行宽=标签+单字段, 默认窗口完整显示, 高度换宽度);
      页3 Z基准值标签缩短。nx_std_config.py 冗余段去重(补丁重复应用所致,
      三段 STD_MAX_ANCHORS 只留一段, 行为不变)。
v1.20:

v1.20: 对话框尺寸策略探查结果写独立脚印文件 nx_dialog_debug.txt(批量
      report.txt 不会覆盖), 同时是 show 回调触发证据; 自适应挑
      auto/fit 项不变。
v1.19:

v1.19: ①全部标准件都有恢复默认按钮——无内置默认的件(压线板等新件)恢复
      通用安全默认(全部图层/全半径/FLB顶/仅放置/+Z/零偏移)。
      ②对话框宽度: NX2312 dlx 块模型无宽度属性(官方全属性表已验证),
      唯一钩子=运行时 TopBlock.DialogSizing——show 时读成员表自动挑
      auto/fit 项, 成员表进日志(后续可按实名精确指定)。
v1.18:

v1.18: 修复 v1.17 三连: ①反转按钮裸块不渲染 → 包进组(grp_flip);
      ②宽度: NX 实测不跨会话记对话框尺寸(固定名时代同样每轮要拉宽),
      改用 dlx 内不换行撑宽行把默认宽度直接做够, dlx 回归唯一文件名
      (v1.17 固定名让 NX 旧值记忆死灰复燃 = "标准件默认值又丢失错乱");
      ③枚举运行时写入通道: PropertyList.SetEnum/SetEnumAsString(枚举是
      独立属性类型, SetInteger 类型不符=写不进——恢复默认改不动图层/
      布尔/方向/Z基准的真凶), 逐通道尝试+读回验证。
v1.17:

v1.17: ①第二页"一键反转全部拉伸参数"按钮(40↔-40; 全图层起始/结束+JRT
      起始/结束取负, 三个固定倒圆参数不动)。
      ②dlx 改回固定文件名(v1.14 唯一名让 NX 忘了用户拉宽的窗口尺寸;
      值记忆由 v1.14 修好的首显钩子覆盖保护), 2/3 页宽度拉一次即记住。
      ③JRT 开链修复(123.dxf 一案): 手动拉伸能成功而脚本判开——
      断口≤1mm 的开链自动合并+小缝桥接(实测 0.24mm 接缝两处, 桥接线
      打标记随重跑清理); 缺边级大缺口(25mm)【不桥】——直线桥会横穿
      其它轮廓包出数倍体积怪条/无效截面(实测一案), 放弃并记断口坐标
      供 2D 补线。④JRT 倒圆异形检测(01.prt 一案): 每轮倒圆前记撤销
      标记, 倒圆后体积校验(丢体>2%=异形), 异形即撤销降 R 重试至 R
      下限——嵌入端/齐平端同套(_edge_blend_end_retry)。
      ⑤JRT 删面收紧: 只认半径≈倒圆R 的圆柱面+距离门控(期刊面中心距
      连接线≈1), 任一连接线找不到可信面即整组放弃——删错面毁条一案。
v1.16:

v1.16: 标准件参数窗口(第三页)每件组默认展开(此前 collapsed=True 每件
      都要点开, 用户反馈改回展开)。
v1.15:

v1.15: ①枚举读取通道回归——v1.14 引入的 GetProperties().GetInteger 与
      界面脱钩(写到属性副本, OK 收集时读到初始 0 → 窗口③所有下拉回第
      0 项: 图层=全部/半径0~9999/布尔=仅放置, 存进 json 后下轮全图海量
      放置卡死一案)。_enum_idx_of 改回 ValueAsString 标签反查第一优先
      (界面真实显示项), .Value 次之, 属性通道弃用; _set_enum_idx 写后
      不再拿写通道自证。
      ②防卡死护栏: 单件锚点数超 STD_MAX_ANCHORS(config 可调, 默认200)
      直接跳过并日志提示检查规则——空图层+全半径的错规则不再能卡死 NX。
v1.14:
==============================================================================

v1.14: UI 层三大根因修复(自省 ui_probe 实测定位):
      ①首显钩子错名——AddShowHandler 不存在, NX2312 实名
      AddDialogShownHandler; v1.11 起首显补填从未注册, NX 会话保留值
      (旧版写进对话框记忆的 R下限3.6/错乱参数)恢复后无人覆盖 →
      "默认值要按按钮才对/每轮固定错乱/记忆像没生效"的总根因。
      三个窗口全部改挂正确钩子。
      ②枚举赋值通道——恢复默认改不动 图层/布尔/方向/Z基准: 直接
      .Value=int 赋值在 NX2312 失效, 增加 GetProperties().SetInteger
      通道并写后回读验证(_set_enum_idx/_get_enum_idx 双通道)。
      ③唯一 dlx 文件名——NX 对话框记忆按 dlx 文件名存取, 三个窗口
      每次启动换唯一名(毫秒戳)并清理旧文件, 旧值无从恢复。
      外加: 第二页 确定/应用 先校验 DXF 路径存在, 无效弹窗不放行
      (不跳转标准件参数页)。期刊 journal-djk 复核: 点胶口-18 起始点
      -570.189 / 点胶口-25 -413.531 / 大水口族 -420.189 与几何判定
      全部逐位吻合(进 selftest 地面真值)。
v1.13: 规则冗余字段 z 删除(期刊验证无作用; 用户定案)——Z 高度只由

v1.13: 规则冗余字段 z 删除(期刊验证无作用; 用户定案)——Z 高度只由
      z_mode 基准面 + off_z 决定, 界面原"Z偏移2"改名"Z偏移"承接,
      原"Z偏移"(z) 从三处 UI/收集/模式全链移除; sanitize 同步丢弃旧 json
      残留 z 键(不再存盘)。规则字段最终形态: layer/r_min/r_max/z_mode/
      bool_mode/dir/off_x/off_y/off_z。
v1.12
==============================================================================

v1.12: 标准件出厂默认外置到 nx_std_config.py(与本脚本同目录, 注释齐全:
      STD_PART_DEFAULTS 表逐字段说明 layer/r半径/z基准/z偏移/布尔/方向/
      XYZ偏移怎么填, 新增标准件照抄一行即可; 另含热咀族关键词、JRT 三参
      默认)。记忆 schema 与 CONFIG_SCHEMA_VERSION 对应(现=3), 版本不符的
      规则记忆整体失效回默认——一次性清洗点胶口 z_mode=FLB_TOP /
      垫片 bool=PLACE 等历史脏记忆。文件缺失时自动回退内置同款表。
      journal-djk.py 复核: 两点胶口手放起点(-570.189/-413.531)与大圆柱
      顶面圆心几何判定逐位吻合。
v1.11: ① 记忆体系定案: 标准件勾选在窗口①确定即保存、第二页图层参数在窗口②
      收集后即保存(后续任何取消都不丢); 加热条起始/结束也记忆(jrt_se),
      但三个几何参数(blend_r/r_step/r_min)恒默认 3.9/0.1/3.7 永不落盘。
      ② 防错乱: 两窗口统一 _prefill_all 预填 + AddShowHandler 首显补填
      (NX 在 initialize 后恢复会话保留值则被覆盖) + _initializing 守卫
      (预填写值不触发 FLB 联动, 用户单独调过的 LS/RZ/DK/DP 不被盖掉)。
      ③ 默认值定案: 主进胶 放置+减去; 接线盒 CXK/CX顶值; 垫片 DK0-5;
      螺丝 放置+减去; 热咀族 RZ0-15/FLB底; XYZ偏移恒0; 方向+Z插入。
      同类型默认一致(关键词表驱动), 各件记忆独立(用户确认)。
      ④ 点胶口定位点修复: 新参考点规则"顶部小圆柱正下方大圆柱的顶面圆心"
      (_part_big_cyl_top, 半径中位数×20 剔除球面误判), 大水口三型号复现
      期刊 z=-420.189, 点胶口得自身正确值(-25→-413.531)——不再错借大水口库值。
      ⑤ 选件窗口 dlx 写失败时回退"上次勾选∩现有件", 不再迭代 None 崩溃。
v1.10: 接线盒 CXK 规则(2D 图规则重做配套): 新定位图层 CXK(图上只画一条线,
      线中点=放置点) + Z 基准 CX顶值(CX -30~-65 → -30); 参考点=件顶面靠后
      边缘中点(面积最大水平面取最高 z 共面联合 bbox 的 y 最小边中点,
      _part_top_back_center 几何自动判定, 三型号通吃; 期刊 24针 起始点
      (0,830,98.1) 复算一致, 用户确认)。默认规则: 接线盒→CXK/CX顶值/仅放置。
v1.9: ① JRT 恒默认不持久化: 对话框/JSON 不再保存 JRT 五参(旧记忆 r_min=3.6
      漂移覆盖 3.7 的根治), 每次打开=3.9/0.1/3.7, 起始/结束随 FLB 联动。
      ② 规则瘦身(用户定案): 抹掉 ref 参考点/布尔实体/接线盒规则(CX自由头
      锚点、CX_TOP 基准全删)——定位只靠 图层圆心 + X/Y/Z 偏移; 参考点转
      内部库 STD_REF_POINTS(Z 仍用库值, XY 优先件主导轴自动对轴)。
      ③ 布尔实体字段删除: 件内全部实体一起当刀具, 逐工具容错(合并失败
      逐个重试, 零相交工具跳过不毁整次布尔)。④ 执行后移除参数: 全部
      产物体打 CAD3D 属性标记后 RemoveParameters(只要实体; 失败留特征树),
      重跑清理改四类(CAD3D_特征→已标记体→已标记曲线→CAD3D_C_组件)。
      ⑤ JSON schema:2(旧记忆字段已变, 无 schema 一律忽略防污染);
      RetainValue 全 False(根治 SP 下标错位串值)。⑥ 恢复默认按钮:
      标准件参数窗口每件一枚(仅内置默认表命中的件显示, 新件不显示按了
      也不报错), 主窗口 JRT 组一枚(回默认+按 FLB 联动)。⑦ 新默认值表:
      主进胶 DP/0~8/FLB底; 垫片 DK/0~5/FLB顶/放置+减去; 大水口|点胶口|
      热咀 RZ/0~15/FLB底; 螺丝 LS/0~5/FLB顶/放置+减去。
v1.8: ① 标准件改独立体: 放置后提升件内全部实体为工作部件独立体并删除装配
      组件(与用户手工粘贴一致; 根治"两实体被合并成一个"与导航器单节点)。
      ② 布尔只减指定实体(布尔实体 1/2)且刀具体保留(期刊 CopyTools 一致;
      根治 retain 副本叠加)。③ 旋转体自动对轴: XY 取件轴线(根治大水口
      -18/-35 与 -25 参考点差 150 的水平偏移); 螺丝-50 参考点Z=0(诊断实测)。
      ④ 三段式: ①选件 ②主参数(OK只收集) ③标准件参数(每件可收起组+Z基准
      值标签, OK/Apply执行)。⑤ 点胶口=大水口同逻辑(用户确认)。
      ⑥ 提升逐实体容错(主进胶 7 实体一案: 单实体失败不再毁整件)。
v1.7: ① JRT 参数"改了不生效"根因修复: dlx 块 id 与收集构造不一致
      (jrt_blend/jrt_rstep/jrt_rmin vs jrt_blend_r/...)——三处统一为单一数据源
      JRT_FIELDS(块 id="jrt_"+key); r_min 默认 3.7, 标签改"边倒圆R下限"。
      ② 标准件放置规则引擎(期刊 journal-bzj.py 反推): basePoint=锚点−参考点
      (五件参考点实测内置); 新锚点 cx_free_head(CX 自由头端面中心, 接线盒);
      新 z_mode CX_TOP(接线盒 Z=CX 起始距离); 布尔按 bool_body 选实体
      (螺丝=第 2 个实体, 保留件); 数量=图纸锚点数(随图变化)。
      ③ 标准件两段式: 第一段勾选要加载的件(记忆选择, 新件默认不勾,
      取消=中止), 第二段参数页只显示选中件。
v1.6: ① 修复 enum 下拉系统性卡第 0 项(.dlx Value 属性硬编码 0 + 读取健壮化;
      布尔"停用"移到末位, 默认=仅放置) —— 标准件"不出现"的根因。
      ② 颜色/透明度撤出界面, 固定期刊配色(条186/模型78/50%)。
      ③ DP 移入减去组; FLB 两值变动时 LS/RZ/DK/DP/JRT 对话框实时联动
      (LS=FLB; RZ=底+13; DK=顶-3; DP=底+6.7023; JRT=顶,顶-7.5), 联动后可单独改。
      ④ JRT 改"起始/结束距离"(顶侧区间, 底侧自动镜像; 起始=结束即停用),
      旧 JSON 的 depth 自动迁移。
v1.5: JRT 加热条建模 —— 依据用户期刊 journal.py 反推工序, 样板 3Djrttest.prt 为
      验收基准: 每条闭合链 × 板两侧对称直建(等效期刊的镜像舞步): 拉伸(壁偏置
      +拔模, 齐平端→入侵端) → 嵌入端 G1 相切边倒圆(R3.9) → 删远端 2 倒圆面 →
      保件相减切槽 → 齐平端倒圆(失败逐级降半径至 R 下限) → 删远端 2 面(圆顶) →
      着色(加热条 186/模型 78, 透明度 50)。参数在对话框"加热条"组, 入侵深度 0
      停用。不做移除参数(特征树保留, 清理/回滚照常)。
v1.4: 清理安全性 —— 脚本建的曲线打 CAD3D 属性标记, 清理只删带标记的曲线;
      图层 11~70 上的无标记曲线与本次 DXF 做几何指纹比对(重合=旧版遗留产物
      删除重建, 不重合=用户自有图形, 保留并警告)。图层被占用不再误删。
v1.3: 全图导入 —— 所有 DXF 图层(LD/0/JRT/任意)的线/弧/圆都导入 NX 作参照,
      每 DXF 图层一个 NX 图层号(JRT 固定 18, 其余按名排序 19~70 动态分配);
      建模只针对 LAYER_TABLE 图层; 11~70 为脚本保留区(每轮重建, 勿放自有图形)。
      用户不再需要手工导入 DXF(手工导入落在保留区的线会被清理当上一轮产物)。
v1.2: JRT 图层导入(被 v1.3 的全图导入取代)。
v1.1 新增: 标准件放置模块 —— stdparts 目录每个 .prt 一条规则(锚点/筛选/Z基准/布尔),
装配组件方式放置, 需布尔的用提升体对 FLB 切除/合并; 对话框"标准件"组动态生成行。

用途:
    读取 AutoCAD 导出的 2D DXF 图纸, 按图层(FLB/JT/LS/RZ/DK/DP/CX)提取曲线,
    在 NX 中重建曲线并按"起始距离/结束距离"(绝对 Z 值)拉伸成实体:
      - FLB  为基准体(各轮廓独立成体, 作为布尔减目标);
      - JT/DP/CX 普通拉伸;
      - LS/RZ/DK 拉伸时从 FLB 基准体上布尔减去;
      - 某图层 起始==结束==0 → 跳过该图层全部操作;
      - 同层嵌套环(外环+内环)按"内环为孔"处理;
      - stdparts 目录里的标准件按规则放置(圆/圆弧圆心 或 FLB 模型孔轴线为锚点),
        按需执行 减去/放置+减去/合并 布尔。

用法(NX 2312):
    工具 → 日记 → 播放(Journal → Play) → 选本文件 → 弹参数对话框 → 确定/应用执行。
    标准件: 把 .prt 放入脚本旁 stdparts 文件夹, 重开对话框即可配置规则。
    件建模约定: 原点=插入点, +Z=插入方向(每件可 -Z 翻转)。

用法(命令行, 无需 NX, 供自检):
    python nx_extrude_runner.py --selftest               纯几何/解析自测(含 Drawing5.dxf)
    python nx_extrude_runner.py --make-sample-dxf 路径    生成 7 图层合成测试 DXF
    (NX run_journal) --batch                             无对话框直跑(批量冒烟)

设计(移植自本项目 offset_runner.lsp v9.x 的架构):
    - LAYER_TABLE 单表驱动: 默认值/对话框生成/参数应用/执行/统计全部出自这一张表;
    - .dlx 对话框文件由脚本自动生成(同 dt:write-dcl 模式), 写入失败回退 %TEMP%;
    - 每次执行先清理上一轮产物(特征前缀 CAD3D_ + 组件前缀 CAD3D_C_ + 7 个 NX 图层
      上的曲线)再重建(同 dt:purge-layer 模式), 因此流程可反复执行;
    - 全程 UndoMark 包裹, 出错整体回滚(同 UNDO BE/E 模式);
    - 参数记忆到脚本旁 nx_extrude_params.json(含 std_parts 规则)。

图层默认拉伸距离/NX 层号/联动偏移等已外置到 nx_std_config.py(v1.33)。
"""

import io
import json
import math
import os
import sys
import time

# ---------------------------------------------------------------------------
# 用户可编辑配置(nx_std_config.py, 与本脚本同目录)。
# 所有标准件出厂默认/热咀族关键词/JRT 三参默认/schema 版本都在那个文件,
# 注释齐全, 改配置不需要动主脚本。文件缺失或损坏时自动回退内置值
# (脚本保持单文件可运行), 加载结果会在日志里体现。
# ---------------------------------------------------------------------------
# 配置/记忆加载异常记录(启动与流水线入口处提示; 不静默吞错)
_CFG_NOTES = []


def _note(msg):
    """提示入队(去重); 由启动弹窗/流水线日志/自测输出。"""
    if msg not in _CFG_NOTES:
        _CFG_NOTES.append(msg)


def notes():
    """(P0 拆分前置) 提示队列只读快照 —— 消费方统一取这里, 不直接碰全局列表。

    背景: 此前三处消费方(run_pipeline/自测/batch_run)直接迭代全局
    _CFG_NOTES。该列表将来会随规则层搬进 nx_rules, 跨模块共享可变全局是
    拆分地雷(搬走后主脚本这里是 None, 搬到的模块里是另一份)。改走访问器后
    无论底层列表在哪, 消费侧代码不变。语义与旧代码逐字一致(只取快照)。
    """
    return list(_CFG_NOTES)


def _cfg_num(v, default):
    """任意配置值 → float; 类型/值非法(含 nan/inf)回 default, 不崩。"""
    try:
        f = float(v)
        return f if f == f and -1e308 < f < 1e308 else float(default)
    except (TypeError, ValueError):
        return float(default)


def _import_module_from_path(name, path):
    """三级模块加载梯(兼容 NX10 的 Python 3.3.2 缺 importlib.util.spec_*):
      梯1 importlib.util.spec_from_file_location (3.4+, 含 NX12/2312) —— 主路径
      梯2 imp.load_source (3.3, NX10 实机 PY003=AVAILABLE)
      梯3 compile+exec 到 ModuleType (3.x 全兼容兜底, imp 于 3.12 移除后仍可用)
    仅"能力缺失"(ImportError/AttributeError)才下梯; 真实加载错(语法/属性)直接
    抛出, 交由调用方记录, 不掩盖。"""
    ladder_err = None
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(name, path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    except (ImportError, AttributeError) as ex:
        ladder_err = "%s: %s" % (type(ex).__name__, ex)
    try:
        import imp
        if hasattr(imp, "load_source"):
            return imp.load_source(name, path)
    except (ImportError, AttributeError):
        pass
    import types
    with io.open(path, encoding="utf-8") as f:
        src = f.read()
    mod = types.ModuleType(name)
    mod.__file__ = path
    exec(compile(src, path, "exec"), mod.__dict__)
    if ladder_err:
        _note("importlib 不可用(%s), 已用 exec 兜底加载配置。" % ladder_err)
    return mod


def _load_user_config():
    import sys as _sys
    _sys.dont_write_bytecode = True   # 不生成 __pycache__(缓存可删可重建)
    try:                       # 此处尚不能调 script_dir()(定义在后)
        base = os.path.dirname(os.path.abspath(__file__))
    except NameError:
        base = os.path.dirname(os.path.abspath(sys.argv[0]))
    p = os.path.join(base, "nx_std_config.py")
    if not os.path.isfile(p):
        _note("配置文件 nx_std_config.py 不存在, 已回退内置默认。")
        return None
    try:
        mod = _import_module_from_path("nx_std_config", p)
        _ = (mod.CONFIG_SCHEMA_VERSION, len(mod.STD_PART_DEFAULTS),
             mod.JRT_BLEND_R_DEFAULT)
        return mod
    except Exception as ex:    # 语法错/缺关键属性/被占用 → 记录原因, 不静默
        _note("配置文件加载失败(%s: %s), 已整体回退内置默认"
                          "——请检查 nx_std_config.py。" % (type(ex).__name__, ex))
        return None


_USER_CFG = _load_user_config()

# 记忆结构版本: 与 nx_extrude_params.json 里存的 schema 相同才认记忆中的
# 标准件规则; 配置文件里把版本调大即可一次性清洗旧记忆(回出厂默认)。
SCHEMA_VERSION = 2
try:
    SCHEMA_VERSION = (int(_USER_CFG.CONFIG_SCHEMA_VERSION)
                      if _USER_CFG is not None else 2)
except (TypeError, ValueError):
    SCHEMA_VERSION = 2
    _note("CONFIG_SCHEMA_VERSION 非法(应为整数), 按 2 处理。")

# JRT 三参默认(配置文件可改; 永不进记忆; 类型非法回默认不崩)
_JRT_BLEND_R = _cfg_num(getattr(_USER_CFG, "JRT_BLEND_R_DEFAULT", 3.9)
                        if _USER_CFG else 3.9, 3.9)
_JRT_R_STEP = _cfg_num(getattr(_USER_CFG, "JRT_R_STEP_DEFAULT", 0.1)
                       if _USER_CFG else 0.1, 0.1)
_JRT_R_MIN = _cfg_num(getattr(_USER_CFG, "JRT_R_MIN_DEFAULT", 3.7)
                      if _USER_CFG else 3.7, 3.7)

# ============================================================================
# §0 参数表与常量(单一数据源: 新增图层 = 加一行)
# ============================================================================

SCRIPT_VERSION = "1.40"


def _cfg(key, default):
    """读配置项(nx_std_config.py), 缺文件/缺键回默认(=原写死值)。"""
    return getattr(_USER_CFG, key, default) if _USER_CFG is not None \
        else default


def _cfg_int(key, default):
    """读配置项并转 int; 类型/值非法回 default(不崩)。"""
    try:
        return int(_cfg_num(_cfg(key, default), default))
    except (TypeError, ValueError, OverflowError):
        return int(default)

FEATURE_PREFIX = "CAD3D_"          # 本脚本产出的特征名前缀(清理/重建依据)
COMP_PREFIX    = FEATURE_PREFIX + "C_"   # 标准件组件实例名前缀
LOOP_TOL       = 0.01              # 环链端点连接容差(mm)
CHAIN_TOL      = 0.01              # NX Section 链接容差(mm)

# (图层码, 中文说明, 布尔角色) + 图层号/默认距离来自 config(v1.33)
# NX 图层号避开 1(默认层): FLB=NX_LAYER_START 起, JT/LS/RZ/DK/DP/CX 依次+1
_LAYER_DEFS = [
    ("FLB", "分流板", "target"),
    ("JT",  "假体",   "none"),
    ("LS",  "螺丝孔", "subtract"),
    ("RZ",  "热咀孔", "subtract"),
    ("DK",  "点孔",   "subtract"),
    ("DP",  "垫片",   "subtract"),
    ("CX",  "出线槽", "none"),
]
_NX_LAYER_START = _cfg_int("NX_LAYER_START", 11)
_LAYER_DISTS = _cfg("LAYER_START_DEFAULTS", {})
if not isinstance(_LAYER_DISTS, dict):
    _LAYER_DISTS = {}
LAYER_TABLE = []
for _i, (_c, _zh, _role) in enumerate(_LAYER_DEFS):
    _d = _LAYER_DISTS.get(_c, (0.0, 35.0))
    if not isinstance(_d, (list, tuple)) or len(_d) != 2:
        _d = (0.0, 35.0)                 # 距离写成单数字/坏类型 → 回默认
    LAYER_TABLE.append((_c, _zh, _NX_LAYER_START + _i,
                        _cfg_num(_d[0], 0.0), _cfg_num(_d[1], 35.0), _role))
LAYER_CODES   = [r[0] for r in LAYER_TABLE]
# 参考图层: 只导入曲线作手工建模参照, 不参与拉伸。JRT 固定 18 号便于记忆;
# 其余 DXF 图层(LD/0/任意)按名排序从 19 起动态分配(保留区上限 70)。
REF_LAYER_TABLE = [("JRT", "加热条(参考)", _cfg_int("NX_LAYER_JRT", 18))]
DYNAMIC_START  = _cfg_int("NX_LAYER_DYNAMIC_START", 19)  # 动态图层起始号
MANAGED_MIN    = _NX_LAYER_START                      # 管理区下界
MANAGED_MAX    = _cfg_int("NX_LAYER_MAX", 70)         # 上界(每轮重建, 勿放自有图形)
if MANAGED_MAX < MANAGED_MIN:      # 交叉校验: 配反了旧曲线迁移匹配会静默失效
    _note("NX_LAYER_MAX(%d) 小于 NX_LAYER_START(%d), 已按 %d 处理。"
                      % (MANAGED_MAX, MANAGED_MIN, MANAGED_MIN))
    MANAGED_MAX = MANAGED_MIN


def assign_layers(layer_names):
    """DXF 图层名 → NX 图层号: 表内静态号 + 其余按名排序动态分配(19~70)。"""
    mapping = {r[0]: r[2] for r in LAYER_TABLE}
    mapping.update({r[0]: r[2] for r in REF_LAYER_TABLE})
    used = set(mapping.values())
    nxt = DYNAMIC_START
    for name in sorted(n for n in layer_names if n not in mapping):
        while nxt in used:
            nxt += 1
        if nxt > MANAGED_MAX:
            break
        mapping[name] = nxt
        used.add(nxt)
    return mapping
TARGET_CODE   = "FLB"                       # 布尔减目标图层

# 对话框分组: (组id, 组标题, [图层码...]) — 按布尔规则分组
DIALOG_GROUPS = [
    ("grp_flb",   "FLB 分流板（基准体；改动两项后 LS/RZ/DK/DP/JRT 自动联动）", ["FLB"]),
    ("grp_plain", "普通拉伸图层（JT 随 FLB 联动；起始=结束=0 则跳过）", ["JT", "CX"]),
    ("grp_sub",   "拉伸并从 FLB 减去（随 FLB 联动，可单独改）", ["LS", "RZ", "DK", "DP"]),
]

# FLB 联动规则: FLB 两值变动时按此刷新下列层(对话框 update_cb 实时联动,
# 联动后各层仍可单独修改)。以 top=max(s,e)/bottom=min(s,e) 为基:
_LINK_OFFSETS_RAW = _cfg("LINK_OFFSETS", {})
if not isinstance(_LINK_OFFSETS_RAW, dict):
    _LINK_OFFSETS_RAW = {}             # 写成非 dict → 回默认, 不崩
_LINK_OFFSETS = {_k: _cfg_num(_LINK_OFFSETS_RAW.get(_k, _d), _d)
                 for _k, _d in (("RZ", 13.0), ("DK", 3.0), ("DP", 6.7023))}
LINK_RULES = {
    "LS":  lambda top, bottom: (top, bottom),            # 与 FLB 相同
    "RZ":  lambda top, bottom: (bottom + _LINK_OFFSETS["RZ"], bottom),
    "DK":  lambda top, bottom: (top, top - _LINK_OFFSETS["DK"]),
    "DP":  lambda top, bottom: (bottom + _LINK_OFFSETS["DP"], bottom),
}
JRT_FROM_TOP = _cfg_num(_cfg("JRT_INTRUSION_DEFAULT", 7.5), 7.5)

# JT 联动模式(v1.37): config JT_LINK_MODES 提供{模式名: (起偏移, 止偏移)},
# JT 起 = FLB top + 起偏移, JT 止 = FLB bottom + 止偏移; 缺失/坏行回内置。
_JT_LINK_FALLBACK = {"普通模式": (10.0, -15.0), "针阀模式": (15.0, -15.0)}
JT_LINK_MODES = dict(_JT_LINK_FALLBACK)
_JT_RAW = _cfg("JT_LINK_MODES", None)
if isinstance(_JT_RAW, dict) and _JT_RAW:
    _jt = {}
    for _k, _v in _JT_RAW.items():
        try:
            _a, _b = float(_v[0]), float(_v[1])
        except Exception:
            continue
        if _a == _a and _b == _b:
            _jt[str(_k)] = (_a, _b)
    if _jt:
        JT_LINK_MODES = _jt
    else:
        _note("JT_LINK_MODES 无有效行, 回退内置两种模式。")
JT_LINK_DEFAULT = str(_cfg("JT_LINK_DEFAULT", "普通模式"))
if JT_LINK_DEFAULT not in JT_LINK_MODES:
    JT_LINK_DEFAULT = next(iter(JT_LINK_MODES))
    _note("JT_LINK_DEFAULT 模式名无效, 回退 %s。" % JT_LINK_DEFAULT)
JT_LINK_OPTS = [(k, k) for k in JT_LINK_MODES]


# CX 联动(v1.38): CX 起始恒=JT 起始; CX 结束 = CX 起始 − 偏移(槽深固定, 随自身
# 顶面走; 不再跟 JT 结束——JT 结束会随联动模式漂移, 不适合作槽底基准)。
# config CX_LINK_END_OFFSET 可改, 默认 35; CX 起始 -30 → 结束 -65。
_CX_LINK_END_OFF = _cfg_num(_cfg("CX_LINK_END_OFFSET", 35.0), 35.0)

# ---------------------------------------------------------------------------
# 标准件规则(stdparts 目录每 .prt 文件一条; 选项表 = 值/中文标签, 对话框按序号映射)
# ---------------------------------------------------------------------------
STDPARTS_DIRNAME = str(_cfg("STDPARTS_DIRNAME", "stdparts"))




# 标准件规则默认值(v1.30: ref 必填, 用户在 config 按文件名填写;
# 无 ref → _rule_usable=False → 该件跳过不用并提示)
DEFAULT_STD_RULE = {"layer": "", "r_min": 0.0, "r_max": 9999.0,
                    "z_mode": "FLB_TOP",
                    "bool_mode": "PLACE", "dir": "+Z",
                    "off_x": 0.0, "off_y": 0.0, "off_z": 0.0,
                    "ref": None}

# 加热条(JRT)参数默认值(三几何参数恒此值不进记忆; 起始/结束随 FLB 联动)
DEFAULT_JRT = {
    "start": 0.0, "end": -7.5,
    "blend_r": _JRT_BLEND_R,
    "r_step": _JRT_R_STEP,
    "r_min": _JRT_R_MIN,
    "offset": _cfg_num(_cfg("JRT_OFFSET", 5.0), 5.0),
    "draft": _cfg_num(_cfg("JRT_DRAFT", 2.0), 2.0),
    "color_strip": _cfg_int("JRT_COLOR_STRIP", 186),
    "color_model": _cfg_int("JRT_COLOR_MODEL", 78),
    "translucency": _cfg_int("JRT_TRANSLUCENCY", 50),
}

# Z 基准选项表(v1.32): 由 config 的 ZMODE_DEFS 生成(用户可自行新增
# 基准模式, 加一行即生效); config 缺失/缺键/行格式坏 → 兜底内置三行。
_ZMODE_FALLBACK = [("FLB_TOP", "FLB顶面", "FLB", "TOP"),
                   ("FLB_BOTTOM", "FLB底面", "FLB", "BOTTOM"),
                   ("CX_TOP", "CX顶值", "CX", "TOP")]
_ZMODE_DEFS = list(_ZMODE_FALLBACK)
if _USER_CFG is not None:
    _zm = []
    for _row in (getattr(_USER_CFG, "ZMODE_DEFS", None) or []):
        try:
            _k, _lbl, _ly, _sd = _row
            _zm.append((str(_k), str(_lbl), str(_ly), str(_sd)))
        except (TypeError, ValueError):
            continue                   # 单行格式坏 → 跳过该行
    if _zm:
        _ZMODE_DEFS = _zm
    else:
        _note("ZMODE_DEFS 为空或无有效行, 回退内置三种基准。")


def zmode_defs():
    """(P0 拆分前置) Z 基准表只读快照 —— sanitize/_std_z/选项表/自测统一取这里。

    背景: 此前消费方直接引用全局 _ZMODE_DEFS, 自测还临时 append/pop 该全局表
    验证"动态加基准"。该表将来随规则层搬进 nx_rules, 跨模块共享可变全局表是
    拆分地雷。改走访问器 + 下方 temporary_zmode 上下文管理器后语义逐字不变。
    """
    return list(_ZMODE_DEFS)


class temporary_zmode(object):
    """临时向 Z 基准表追加一行, 退出时必还原(异常也不污染全局), 仅供自测。

    等价于旧代码的手工 try/finally append/pop, 但把"用完必还原"固化成上下文
    管理器, 拆分后测试代码不依赖全局表的物理位置。
    """

    def __init__(self, row):
        self._row = tuple(row)

    def __enter__(self):
        _ZMODE_DEFS.append(self._row)
        return self

    def __exit__(self, *exc_info):
        try:
            _ZMODE_DEFS.remove(self._row)
        except ValueError:
            pass
        return False


ZMODE_OPTS     = [(k, lbl + "+偏移") for k, lbl, _ly, _sd in zmode_defs()]
BOOL_OPTS      = [("PLACE", "仅放置"), ("PLACE_SUBTRACT", "放置+减去"),
                  ("SUBTRACT", "仅减去(隐藏件)"), ("UNITE", "合并进FLB")]
DIR_OPTS       = [("+Z", "+Z插入"), ("-Z", "-Z翻转")]
LAYER_SEL_OPTS = ([("", "全部图层")]
                  + [(c, c) for c in LAYER_CODES]
                  + [("CXK", "CXK(接线盒线)")])


# JRT 对话框字段单一数据源: (key, 中文标签)
JRT_FIELDS = [
    ("start", "起始距离"),
    ("end", "结束距离"),
    ("blend_r", "边倒圆R"),
    ("r_step", "R降级步长"),
    ("r_min", "边倒圆R下限"),
]

# 单件最大放置数量护栏(nx_std_config.STD_MAX_ANCHORS 可调; 非法回默认)
STD_MAX_ANCHORS = (_cfg_int("STD_MAX_ANCHORS", 200))


def script_dir():
    """脚本所在目录(journal 播放时 sys.argv[0] 即本文件路径)。"""
    try:
        return os.path.dirname(os.path.abspath(__file__))
    except NameError:
        return os.path.dirname(os.path.abspath(sys.argv[0]))


# ============================================================================
# ============================================================================
# §1.5 子模块加载器(P1 起): 按绝对路径加载同目录纯逻辑模块并注入共享符号
# ============================================================================
#
# 设计契约(详见 docs/模块拆分实施计划.md §1):
#   - 子模块禁止 import 兄弟模块, 跨模块依赖一律由主脚本注入为模块属性;
#   - 复用 _import_module_from_path 三级梯(NX10 无 importlib.util / 3.12 无
#     imp 均已覆盖), 按绝对路径加载, 不依赖 sys.path / cwd;
#   - 子模块缺失 = 立即抛错, 绝不静默回退。
_LOADED_SUB = {}


def _sub_path(name):
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), name + ".py")


def _load_sub(name):
    """按绝对路径加载同目录子模块(纯逻辑层)。加载失败直接抛, 不掩盖。"""
    mod = _import_module_from_path(name, _sub_path(name))
    sys.modules[name] = mod
    _LOADED_SUB[name] = mod
    return mod


def _inject(mod, **kw):
    for _k, _v in kw.items():
        setattr(mod, _k, _v)
    return mod


# nx_geom: DXF 解析 + 环链几何 + 几何指纹(纯 Python, 无 NX 依赖)
_nx_geom = _inject(_load_sub("nx_geom"),
                   LAYER_CODES=LAYER_CODES,
                   LOOP_TOL=LOOP_TOL)

# 再导出(外部消费者 test/test_batch111.py 用 m.parse_dxf; 内部 build_layer/
# build_jrt/nx_purge/selftest 均按原名字可见, 零改动):
DXLine = _nx_geom.DXLine
DXArc = _nx_geom.DXArc
DXCircle = _nx_geom.DXCircle
_read_dxf_text = _nx_geom._read_dxf_text
parse_dxf = _nx_geom.parse_dxf
_pkey = _nx_geom._pkey
_near_keys = _nx_geom._near_keys
find_chains = _nx_geom.find_chains
loop_polygon = _nx_geom.loop_polygon
poly_area = _nx_geom.poly_area
_bbox = _nx_geom._bbox
point_in_poly = _nx_geom.point_in_poly
_loop_in_loop = _nx_geom._loop_in_loop
organize_loops = _nx_geom.organize_loops
_q = _nx_geom._q
_nx_curve_fp = _nx_geom._nx_curve_fp
_dxf_ent_fp = _nx_geom._dxf_ent_fp
dxf_fingerprints = _nx_geom.dxf_fingerprints

# nx_rules: 标准件规则 / 分层联动 / 参数记忆(纯逻辑, 无 NX 依赖)
_nx_rules = _inject(_load_sub("nx_rules"),
                    script_dir=script_dir,
                    STDPARTS_DIRNAME=STDPARTS_DIRNAME,
                    DEFAULT_STD_RULE=DEFAULT_STD_RULE,
                    DEFAULT_JRT=DEFAULT_JRT,
                    STD_MAX_ANCHORS=STD_MAX_ANCHORS,
                    SCHEMA_VERSION=SCHEMA_VERSION,
                    _USER_CFG=_USER_CFG,
                    LAYER_CODES=LAYER_CODES,
                    LAYER_TABLE=LAYER_TABLE,
                    TARGET_CODE=TARGET_CODE,
                    LOOP_TOL=LOOP_TOL,
                    LINK_RULES=LINK_RULES,
                    JRT_FROM_TOP=JRT_FROM_TOP,
                    JT_LINK_MODES=JT_LINK_MODES,
                    JT_LINK_DEFAULT=JT_LINK_DEFAULT,
                    _JT_LINK_FALLBACK=_JT_LINK_FALLBACK,
                    _CX_LINK_END_OFF=_CX_LINK_END_OFF,
                    BOOL_OPTS=BOOL_OPTS,
                    DIR_OPTS=DIR_OPTS,
                    zmode_defs=zmode_defs,
                    _note=_note,
                    _cfg_num=_cfg_num)

# 再导出 nx_rules(外部消费者 test/test_batch111.py 用 m.guess_std_rule /
# m.sanitize_std_rule / m.collect_circle_anchors; 内部 build_layer/place_std_parts/
# 对话框/自测 均按原名字可见, 零改动):
_jt_link_values = _nx_rules._jt_link_values
jt_mode_with_memory = _nx_rules.jt_mode_with_memory
_cx_link_values = _nx_rules._cx_link_values
derive_linked = _nx_rules.derive_linked
jrt_with_memory = _nx_rules.jrt_with_memory
anchors_overflow = _nx_rules.anchors_overflow
stdparts_dir = _nx_rules.stdparts_dir
std_part_defaults = _nx_rules.std_part_defaults
guess_std_rule = _nx_rules.guess_std_rule
sanitize_std_rule = _nx_rules.sanitize_std_rule
_rule_usable = _nx_rules._rule_usable
_unusable_names = _nx_rules._unusable_names
discover_std_parts = _nx_rules.discover_std_parts
merge_std_rules = _nx_rules.merge_std_rules
merge_jrt = _nx_rules.merge_jrt
default_params = _nx_rules.default_params
set_json_path_provider = _nx_rules.set_json_path_provider
set_stdparts_lister = _nx_rules.set_stdparts_lister
_json_path = _nx_rules._json_path
load_state = _nx_rules.load_state
_name_list = _nx_rules._name_list
save_state = _nx_rules.save_state
merge_params = _nx_rules.merge_params
resolve_dxf_path = _nx_rules.resolve_dxf_path
_place_delta = _nx_rules._place_delta
_center_seen = _nx_rules._center_seen
collect_circle_anchors = _nx_rules.collect_circle_anchors
_std_z = _nx_rules._std_z
# nx_dlx: .dlx 对话框生成器(纯字符串模板)
_nx_dlx = _inject(_load_sub("nx_dlx"),
                  LAYER_TABLE=LAYER_TABLE,
                  DIALOG_GROUPS=DIALOG_GROUPS,
                  JRT_FIELDS=JRT_FIELDS,
                  MANAGED_MIN=MANAGED_MIN,
                  MANAGED_MAX=MANAGED_MAX,
                  DEFAULT_JRT=DEFAULT_JRT,
                  ZMODE_OPTS=ZMODE_OPTS,
                  BOOL_OPTS=BOOL_OPTS,
                  DIR_OPTS=DIR_OPTS,
                  LAYER_SEL_OPTS=LAYER_SEL_OPTS,
                  JT_LINK_OPTS=JT_LINK_OPTS,
                  script_dir=script_dir,
                  _std_z=_std_z,
                  default_params=default_params)

# 再导出(外部消费者 tools/nx_zero_ref.py 用 build_selection_dlx/_fresh_dlx_path;
# 内部 build_dlx/write_dlx 等按原名可见, 零改动):
_esc = _nx_dlx._esc
_blk_double = _nx_dlx._blk_double
_blk_label = _nx_dlx._blk_label
_blk_button = _nx_dlx._blk_button
_blk_filebrowser = _nx_dlx._blk_filebrowser
_blk_enum = _nx_dlx._blk_enum
_blk_toggle = _nx_dlx._blk_toggle
build_selection_dlx = _nx_dlx.build_selection_dlx
_group_item = _nx_dlx._group_item
_opt_index = _nx_dlx._opt_index
build_dlx = _nx_dlx.build_dlx
build_std_dlx = _nx_dlx.build_std_dlx
_logs_dir = _nx_dlx._logs_dir
_fresh_dlx_path = _nx_dlx._fresh_dlx_path
_temp_dlx_path = _nx_dlx._temp_dlx_path
write_std_dlx = _nx_dlx.write_std_dlx
write_dlx = _nx_dlx.write_dlx

# ============================================================================
# §4 参数记忆(nx_extrude_params.json) —— 已搬至 nx_rules.py, 由加载器再导出
# ============================================================================



# ============================================================================
# §5 NX 建模流水线(NXOpen 延迟导入; 批量/自测模式不触发)
# ============================================================================

# 本会话创建的特征登记(名字可能被 NX 自动改尾号导致前缀清理漏网, 双保险)
#
# (P0 拆分前置) 原为模块级裸列表 _CREATED_FEATURES —— 6 处 append 分散在
# 拉伸/提升/布尔/边倒圆/删面五个工序, 2 处清空在 nx_purge 与 _remove_parameters,
# 是全局可变状态里扇入最高的一处, 也是模块拆分的最大地雷(拆开后两个模块各持
# 一份 → 清理漏删上一轮产物 或 误删用户图形)。升级为显式对象后: 谁持有
# registry 谁负责, 调用语义逐字不变。兼容别名见下, 改口完成后删除。
class FeatureRegistry(object):
    """本会话创建特征的登记表(语义等价于原模块级列表 _CREATED_FEATURES)。"""

    def __init__(self):
        self._items = []

    def add(self, feat):
        """登记一个特征; None 忽略(调用侧 try 内可能拿到 None)。"""
        if feat is not None:
            self._items.append(feat)

    def all(self):
        """只读快照(遍历用, 不清空)。"""
        return list(self._items)

    def take(self):
        """取出全部并清空(nx_purge 的"登记表双保险"路径: 取走即归零)。"""
        out = list(self._items)
        del self._items[:]
        return out

    def clear(self):
        """清空(移除参数后特征已不存在, 登记表作废)。"""
        del self._items[:]

    def __len__(self):
        return len(self._items)


registry = FeatureRegistry()

# 脚本曲线所有权标记(NX 对象属性): 清理只删带标记的曲线, 用户自有图形不受影响
MARK_ATTR = "CAD3D"


def _mark_curve(obj):
    try:
        obj.SetAttribute(MARK_ATTR, SCRIPT_VERSION)
    except Exception:
        pass


def _is_marked(obj):
    try:
        return bool(obj.GetStringAttribute(MARK_ATTR))
    except Exception:
        return False


# 几何指纹(_q/_nx_curve_fp/_dxf_ent_fp/dxf_fingerprints)已搬至 nx_geom.py,
# 由上方加载器再导出(同名可见, 调用方零改动)。

def _iter(coll):
    """NX 集合迭代: for-in 优先, 失败退 GetObjects()。"""
    try:
        return list(coll)
    except TypeError:
        try:
            return list(coll.GetObjects())
        except Exception:
            return []


def _bodies_of(feat):
    for getter in ("GetBodies", "GetEntities"):
        try:
            arr = getattr(feat, getter)()
            if arr:
                return [b for b in arr]
        except Exception:
            continue
    return []


def _fmt_num(v):
    return ("%.4f" % float(v)).rstrip("0").rstrip(".") or "0"


class Log(object):
    """日志收集器: 逐行进 ListingWindow(NX 内)并缓存供报告。"""
    def __init__(self, session=None):
        self.lines = []
        self.session = session
        if session is not None:
            try:
                session.ListingWindow.Open()
            except Exception:
                pass

    def __call__(self, msg):
        self.lines.append(msg)
        if self.session is not None:
            try:
                self.session.ListingWindow.WriteLine(msg)
            except Exception:
                pass


def nx_purge(session, work_part, log, dxf_layers=None, nx=None):
    """清理上一轮产物(只删自己的东西, 不碰用户图形):
    - 特征: CAD3D_ 前缀 + 本会话登记表(按所属部件过滤);
    - 已标记体: v1.9 移除参数后留下的哑体(特征已删, 按 CAD3D 属性标记
      识别; 特征删除时宿主体一并消失, 在特征/曲线/组件删除并更新后
      二次枚举, 只补删幸存的);
    - 组件: CAD3D_C_ 前缀实例;
    - 曲线: 带 CAD3D 标记属性的(任何图层); 11~70 内无标记的曲线与本次 DXF
      几何指纹比对 —— 重合=旧版(v1.2/v1.3)无标记产物, 删除重建;
      不重合=用户自有图形, 保留并警告。

    返回实际删除对象数(仅供诊断; 调用方目前忽略返回值)。

    (P0) nx: 显式传入 NXOpen 模块引用(调用方 run_pipeline 传它已 import 的)。
    此前本函数 `global NXOpen` 依赖 run_pipeline 在入口赋值全局——跨模块的
    隐式依赖, 拆分后必然断链; 缺省时自行 import, 旧调用点行为不变。
    """
    if nx is None:
        import NXOpen as nx
    feats, curves, comps = [], [], []
    try:
        for f in _iter(work_part.Features):
            if str(getattr(f, "Name", "")).startswith(FEATURE_PREFIX):
                feats.append(f)
    except Exception as ex:
        log("【清理】特征枚举失败: %s" % ex)
    # (P0) registry.take() 与原 "list(_CREATED_FEATURES) + del[:]" 等价:
    # 取走全部并清空(登记表双保险, 仅本工作部件)
    for f in registry.take():
        try:
            if f not in feats and f.OwningPart == work_part:
                feats.append(f)
        except Exception:
            pass
    try:                                            # 标准件组件实例
        root = work_part.ComponentAssembly.RootComponent
        if root is not None:                        # 纯部件(未成装配)时为 None
            for c in root.GetChildren():
                if str(getattr(c, "Name", "")).startswith(COMP_PREFIX):
                    comps.append(c)
    except Exception as ex:
        log("【清理】组件枚举失败: %s" % ex)

    # 曲线: 带标记的删; 范围内无标记的做指纹迁移匹配
    fps = dxf_fingerprints(dxf_layers)
    kept_warn = {}
    legacy = 0
    try:
        for c in _iter(work_part.Curves):
            try:
                lay = c.Layer
            except Exception:
                continue
            if _is_marked(c):
                curves.append(c)
            elif MANAGED_MAX >= lay >= MANAGED_MIN:
                fp = _nx_curve_fp(c)
                if fp is not None and fps.get(fp, 0) > 0:
                    fps[fp] -= 1                    # 旧版无标记产物 → 删除重建
                    curves.append(c)
                    legacy += 1
                else:
                    kept_warn[lay] = kept_warn.get(lay, 0) + 1
    except Exception as ex:
        log("【清理】曲线枚举失败: %s" % ex)

    if feats or curves or comps:
        try:
            session.UpdateManager.AddToDeleteList(feats + curves + comps)
            session.UpdateManager.DoUpdate(
                session.SetUndoMark(nx.Session.MarkVisibility.Invisible, "CAD3D 清理"))
        except Exception as ex:
            log("【清理】删除失败(可能有特征引用曲线): %s" % ex)
            return 0                    # 返回值=实际删除数, 未删成即 0

    # 已标记哑体: 特征删除后幸存的(移除参数轮产物), 二次枚举补删
    mbodies = []
    try:
        for b in _iter(work_part.Bodies):
            if _is_marked(b):
                mbodies.append(b)
    except Exception as ex:
        log("【清理】实体枚举失败: %s" % ex)
    if mbodies:
        try:
            session.UpdateManager.AddToDeleteList(mbodies)
            session.UpdateManager.DoUpdate(
                session.SetUndoMark(nx.Session.MarkVisibility.Invisible, "CAD3D 清理体"))
        except Exception as ex:
            log("【清理】已标记体删除失败: %s" % ex)
            return len(feats) + len(curves) + len(comps)   # 体未删掉
    log("【清理】已删除上一轮: 特征 %d 个, 实体 %d 个, 曲线 %d 条(含旧版无标记 %d), 组件 %d 个。"
        % (len(feats), len(mbodies), len(curves), legacy, len(comps)))
    if kept_warn:
        log("【清理】警告: 图层 %s 有 %d 条不属于本脚本的曲线, 已保留"
            "(脚本曲线将与其同层混放, 建议移到图层 1~%d 或 %d 以上)。"
            % (",".join(str(k) for k in sorted(kept_warn)),
               sum(kept_warn.values()), MANAGED_MIN - 1, MANAGED_MAX + 1))
    return len(feats) + len(curves) + len(comps) + len(mbodies)


def ensure_categories(work_part, layer_map, log):
    """为各导入图层建同名图层类别(便于用户在图层设置里按名开关)。"""
    cats = getattr(work_part, "LayerCategories", None)
    if cats is None:
        return
    for code, num in sorted(layer_map.items(), key=lambda kv: kv[1]):
        try:
            if cats.FindObject(code) is None:
                cats.CreateCategory(code, "%s (CAD3D)" % code, [num])
        except Exception:
            pass


def create_curves(work_part, layers, layer_map, log):
    """按图层建 NX 曲线(线/弧/圆) — 全部 DXF 图层都导入(建模图层+参考图层)。

    layer_map: {DXF 图层名: NX 图层号}(assign_layers 产物)。
    返回 {code: [曲线对象或 None]} — 列表与 DXF 实体一一对应(失败处为 None),
    保证环链索引不漂移(教训同 v9.1 的 eName 对应关系)。
    """
    import NXOpen as nx

    P3d, V3d = nx.Point3d, nx.Vector3d
    mtx = None
    for _attr in ("Matrices", "PointMatrices"):   # 各版本集合名不同, 兼容取用
        coll = getattr(work_part, _attr, None)
        if coll is not None and hasattr(coll, "CreateMatrix"):
            try:
                mtx = coll.CreateMatrix(nx.NXMatrix3d(
                    1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0))
            except Exception:
                mtx = None
            break

    def make_arc(cx, cy, r, a0, a1):
        c = P3d(cx, cy, 0.0)
        if mtx is not None:
            return work_part.Curves.CreateArc(c, mtx, r, a0, a1)
        return work_part.Curves.CreateArc(c, V3d(1.0, 0.0, 0.0),
                                          V3d(0.0, 1.0, 0.0), r, a0, a1)

    out = {}
    zh = {r[0]: r[1] for r in LAYER_TABLE}
    zh.update({r[0]: r[1] for r in REF_LAYER_TABLE})
    for code in sorted(layers.keys()):
        # 兜底层号: 超出管理区上限未分配的图层落到 MANAGED_MAX(脚本管理区,
        # 每轮重建)而非第 1 层(用户层)——避免污染用户自有图形(v1.35)
        num = layer_map.get(code, MANAGED_MAX)
        ents = layers.get(code) or []
        made, fails = [], 0
        for e in ents:
            obj = None
            try:
                if e.kind == "line":
                    obj = work_part.Curves.CreateLine(P3d(e.p1[0], e.p1[1], 0.0),
                                                      P3d(e.p2[0], e.p2[1], 0.0))
                elif e.kind == "arc":
                    obj = make_arc(e.c[0], e.c[1], e.r, e.a0, e.a1)
                else:  # circle → 整圆弧
                    obj = make_arc(e.c[0], e.c[1], e.r, 0.0, 2.0 * math.pi)
                obj.Layer = num
                _mark_curve(obj)                    # 所有权标记(清理只删自己的)
            except Exception as ex:
                fails += 1
                if fails <= 3:
                    log("  %s 曲线创建失败(%s): %s" % (code, e.kind, ex))
            made.append(obj)
        out[code] = made
        n_ok = len(made) - fails
        if n_ok:
            extra = ("(失败 %d)" % fails) if fails else ""
            log("【曲线】%s(%s): %d 条 → NX 图层 %d %s"
                % (code, zh.get(code, "参考"), n_ok, num, extra))
    return out


def work_part_rules(work_part, curves):
    """曲线列表 → 选择意图规则(BaseCurveDumb: 不做额外链接推断)。"""
    return work_part.ScRuleFactory.CreateRuleBaseCurveDumb(list(curves))


def _add_to_section_compat(section, rules, help_pt):
    """AddToSection 跨版本编组通道(NX10/11/12 与 2312 的唯一差异点)。

    根因(实机探针 v2.1 于 NX10=3.3.2 / NX12=3.6.1 验证): NX2312 的自研绑定会把
    Python None 自动转空指针, 而 NX10/12 绑定要求类型化空对象 NXOpen.NXObject.Null,
    裸 None 会抛 "没有过载与这些参数匹配"(TypeError)。__doc__ 证实签名各版一致:
    AddToSection(rules, seed, startConnector, endConnector, helpPoint, featureMode
    [, chainWithinFeature])。rules 用 Python list、helpPoint 用 Point3d 各版皆可
    (对照 ReplaceRules/CreateLine 实测通过), 故仅 seed/两 connector 需换 null 形态。

    策略: 先按 2312 原式(None)调用 —— 现网 2312 路径逐字节不变、零回归; 仅当抛
    异常(旧版)才用 NXObject.Null 重试。重试的异常不吞, 让真实几何错误正常上抛。"""
    import NXOpen as nx
    try:
        section.AddToSection(rules, None, None, None, help_pt,
                             nx.Section.Mode.Create, False)
        return
    except Exception:
        pass
    null = getattr(nx.NXObject, "Null", None)
    section.AddToSection(rules, null, null, null, help_pt,
                         nx.Section.Mode.Create, False)


def _sc_rule_options(work_part):
    """ScRuleFactory.CreateRuleOptions 仅 NX2312 等新版本有; NX10/12 该属性不存在
    (实机探针 v2.1: AttributeError), 且旧版 CreateRuleFaceDumb/CreateRuleOuterEdges
    OfFaces 只有"不收 ruleOptions"的单参重载(__doc__ 证实)。取不到返回 None, 调用方
    据此走无 opts 通道 —— 2312 仍传 opts(现网零回归), 旧版自动降级。"""
    try:
        opts = work_part.ScRuleFactory.CreateRuleOptions()
    except Exception:
        return None
    try:
        opts.SetSelectedFromInactive(False)
    except Exception:
        pass
    return opts


def _set_expr(expr, value_str):
    """跨版本写 NXOpen.Expression 公式。

    NX2312 的 Expression 有 SetFormula(str)；NX10/12 绑定无该方法(实机端到端报
    'NXOpen.Expression' object has no attribute 'SetFormula')，改用 .RightHandSide
    =str(与本文件 Limits 各处同款, 旧版可用)。先试 SetFormula 保证 2312 零回归。"""
    try:
        expr.SetFormula(value_str)
    except Exception:
        expr.RightHandSide = value_str


def extrude_curves(work_part, curves, start, end, name, bool_op=None, help_pt=None,
                   offset=None, draft=None):
    """拉伸一组封闭环曲线: start/end 为绝对 Z 距离。

    bool_op: None=普通创建; ("subtract"/"unite", 目标体)=拉伸时布尔。
    offset: (start, end) 单侧壁偏置(如 (0,5)=壁厚5, 同期刊); draft: 拔模角(度)。
    """
    import NXOpen as nx
    import NXOpen.Features             # 子模块必须显式 import, 否则包属性不存在
    import NXOpen.GeometricUtilities

    bldr = work_part.Features.CreateExtrudeBuilder(nx.Features.Feature.Null)
    try:
        section = work_part.Sections.CreateSection(CHAIN_TOL, CHAIN_TOL, 0.5)
        try:
            section.SetAllowedEntityTypes(nx.Section.AllowTypes.OnlyCurves)
        except Exception:
            pass
        bldr.Section = section
        bldr.AllowSelfIntersectingSection(True)
        rules = [work_part_rules(work_part, curves)]
        hp = help_pt
        if hp is None:
            try:
                hp = curves[0].StartPoint
            except Exception:          # 某些曲线类型该属性取值会抛错
                hp = nx.Point3d(0.0, 0.0, 0.0)
        _add_to_section_compat(section, rules, hp)

        bldr.Limits.StartExtend.Value.RightHandSide = _fmt_num(start)
        bldr.Limits.EndExtend.Value.RightHandSide = _fmt_num(end)
        bldr.DistanceTolerance = CHAIN_TOL
        if offset is not None:
            _set_expr(bldr.Offset.StartOffset, _fmt_num(offset[0]))
            _set_expr(bldr.Offset.EndOffset, _fmt_num(offset[1]))
        if draft is not None:
            _set_expr(bldr.Draft.FrontDraftAngle, _fmt_num(draft))
            _set_expr(bldr.Draft.BackDraftAngle, _fmt_num(draft))
        bldr.Direction = work_part.Directions.CreateDirection(
            nx.Point3d(0.0, 0.0, 0.0), nx.Vector3d(0.0, 0.0, 1.0),
            nx.SmartObject.UpdateOption.DontUpdate)
        try:
            bldr.BodyType = nx.Features.Feature.BodyType.Solid
        except Exception:
            pass

        btype = nx.GeometricUtilities.BooleanOperation.BooleanType
        if bool_op is not None:
            op_name, target = bool_op
            bldr.BooleanOperation.Type = (btype.Subtract if op_name == "subtract"
                                          else btype.Unite)
            bldr.BooleanOperation.SetTargetBodies([target])
        else:
            bldr.BooleanOperation.Type = btype.Create

        feat = bldr.CommitFeature()
        try:
            feat.SetName(name)
        except Exception:
            pass
        registry.add(feat)
        return feat
    finally:
        try:
            bldr.Destroy()
        except Exception:
            pass


def modeling_ents(layers, code):
    """建模用 DXF 实体: CX 并入 CXK 的曲线一起找闭环。

    (用户定案: CXK 层唯一用途=接线盒定位线; 2D 新规则下 CX 单独不成环,
    CX+CXK 才恢复过去的闭环。)返回列表, 与 nx_curves_by_ent 同序拼接。
    """
    ents = list(layers.get(code) or [])
    if code == "CX" and (layers.get("CXK") or []):
        ents += list(layers["CXK"])
    return ents


def build_layer(session, work_part, code, zh, role, layers, nx_curves_by_ent,
                params, flb_regions, log, stats):
    """单图层建模: 环组织 → 拉伸 → 布尔。

    FLB(target) 各轮廓独立成体并登记 (体, 包围盒) — NX 的拉伸时"合并"对不相交
    轮廓只会生成独立体, 因此不做合并; subtract 层按工具位置从包围盒匹配目标体。
    返回 (bodies, regions): regions 仅 target 层非空, 供 subtract 层匹配。
    """
    import NXOpen as nx

    start, end = params[code]
    ents = modeling_ents(layers, code)
    ncurves = len(ents)
    stats[code] = {"curves": ncurves, "profiles": 0, "features": 0, "bodies": [],
                   "note": ""}

    if abs(start) < 1e-12 and abs(end) < 1e-12:
        stats[code]["note"] = "距离全 0, 跳过"
        log("【%s】起始=结束=0, 跳过该图层。" % code)
        return [], []
    if start > end:
        start, end = end, start
        stats[code]["note"] = "起始>结束, 已交换"
        log("【%s】起始>结束, 已自动交换为 %.4g→%.4g。" % (code, start, end))
    if abs(end - start) < 1e-12:
        stats[code]["note"] = "零厚度, 跳过"
        log("【%s】起始==结束(非零), 零厚度无法拉伸, 跳过。" % code)
        return [], []
    if not ents:
        stats[code]["note"] = "图层无曲线"
        log("【%s】DXF 中无该图层曲线(距离 %.4g→%.4g), 跳过。" % (code, start, end))
        return [], []

    profiles, opens, _nc = organize_loops(ents)
    stats[code]["profiles"] = len(profiles)
    if opens:
        log("【%s】警告: %d 条开口链未闭合, 不参与拉伸。" % (code, len(opens)))
    if not profiles:
        stats[code]["note"] = "无封闭环"
        log("【%s】未找到任何封闭环, 跳过拉伸。" % code)
        return [], []

    def pick_region(bbox):
        """按轮廓中心点在登记的 FLB 区域里找包含它的体。"""
        cx = (bbox[0] + bbox[2]) / 2.0
        cy = (bbox[1] + bbox[3]) / 2.0
        for body, b in flb_regions:
            if b[0] <= cx <= b[2] and b[1] <= cy <= b[3]:
                return body
        return None

    nx_curves = modeling_ents(nx_curves_by_ent, code)   # 与 ents 同序拼接
    bodies, regions = [], []
    fi = 0

    def chain_curves(item):
        """环条目 → NX 曲线对象列表; 含创建失败(None)则返回 None。"""
        if item.get("chain") is not None:
            idxs = [i for (i, _r) in item["chain"]]
        else:
            idxs = [ents.index(item["circle"])]
        cs = [nx_curves[i] for i in idxs]
        if any(c is None for c in cs):
            log("【%s】轮廓含创建失败的曲线, 该轮廓跳过。" % code)
            return None
        return cs

    def chain_help(item):
        """环上一点(DXF 几何直接算, 作 Section helpPoint)。"""
        if item.get("chain") is not None:
            e = ents[item["chain"][0][0]]
            p = e.p1 if e.kind != "circle" else (e.c[0] + e.r, e.c[1])
        else:
            c = item["circle"]
            p = (c.c[0] + c.r, c.c[1])
        return nx.Point3d(p[0], p[1], 0.0)

    for prof in profiles:
        fi += 1
        base_name = "%sEXT_%s_%d" % (FEATURE_PREFIX, code, fi)
        outer_curves = chain_curves(prof["outer"])
        if outer_curves is None:
            continue
        hp = chain_help(prof["outer"])
        holes = prof["holes"]

        # 外环的拉伸时布尔: subtract 层从位置匹配的 FLB 体减去, 其余普通创建
        op = None
        pick = None
        if role == "subtract":
            if flb_regions:
                pick = pick_region(prof["outer"]["bbox"])
                if pick is not None:
                    op = ("subtract", pick)
                else:
                    log("【%s】轮廓 %d 不落在任何 FLB 体内, 按普通拉伸保留。"
                        % (code, fi))
            else:
                log("【%s】无 FLB 基准体, 轮廓按普通拉伸保留。" % code)
        try:
            feat = extrude_curves(work_part, outer_curves, start, end,
                                  base_name + ("_OUT" if holes else ""),
                                  bool_op=op, help_pt=hp)
            stats[code]["features"] += 1
        except Exception as ex:
            stats[code]["note"] = "拉伸失败"
            log("【%s】轮廓 %d 拉伸失败: %s" % (code, fi, ex))
            continue
        got = _bodies_of(feat)
        if op is None:
            bodies.extend(got)
        if role == "target" and got:
            regions.append((got[0], prof["outer"]["bbox"]))

        # 孔(同层嵌套内环)处理
        for k, hole in enumerate(holes):
            hc = chain_curves(hole)
            if hc is None:
                continue
            if op is not None:
                # 外环已从 FLB 减去整盘, 内环(芯)并回被减的 FLB 体 → 净效果为环形腔
                hop = ("unite", pick)
                hname = base_name + "_CORE%d" % k
            else:
                host = got[0] if got else None
                if host is None:
                    continue
                hop = ("subtract", host)
                hname = base_name + "_H%d" % k
            try:
                extrude_curves(work_part, hc, start, end, hname,
                               bool_op=hop, help_pt=chain_help(hole))
                stats[code]["features"] += 1
            except Exception as ex:
                stats[code]["note"] = "孔处理失败"
                log("【%s】轮廓 %d 孔 %d 处理失败: %s" % (code, fi, k, ex))

    if role == "target":
        log("【%s】基准体完成: %d 个轮廓(体 %d 个), %.4g→%.4g。"
            % (code, len(profiles), len(regions), start, end))
    elif role == "subtract":
        log("【%s】布尔减完成: %d 个轮廓(从 FLB 减去)。" % (code, len(profiles)))
    else:
        log("【%s】拉伸完成: %d 个轮廓。" % (code, len(profiles)))
    stats[code]["bodies"] = bodies
    return bodies, regions


# ---------------------------------------------------------------------------
# 标准件放置(§5.5): 锚点收集 → AddComponent → 按需提升体+布尔
# ---------------------------------------------------------------------------

def _matrix3x3(nx, flip):
    """放置姿态: 单位阵(+Z 插入) 或绕 X 180°(-Z 插入)。"""
    vals = ((1.0, 0.0, 0.0, 0.0, -1.0, 0.0, 0.0, 0.0, -1.0) if flip
            else (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0))
    try:
        return nx.Matrix3x3(*vals)
    except TypeError:
        m = nx.Matrix3x3()
        for name, v in zip(("Xx", "Xy", "Xz", "Yx", "Yy", "Yz", "Zx", "Zy", "Zz"), vals):
            setattr(m, name, v)
        return m


# 放置/锚点/Z 基准纯逻辑(_place_delta/_center_seen/collect_circle_anchors/
# _std_z)已搬至 nx_rules.py, 由加载器再导出(同名可见, 调用方零改动)。

def _pick_target(flb_regions, cx, cy, log=None):
    """按锚点 XY 找包含它的 FLB 体。

    多个 FLB 体(多通道板)时必须命中包围盒; 一个都命中不了才兜底取第一个
    体——此时切错板的风险很高, 因此兜底一定要在日志里留痕(v1.29: 过去
    是静默兜底, 板外锚点会把孔切到别的板上且无任何提示)。
    """
    for body, b in flb_regions:
        if b[0] <= cx <= b[2] and b[1] <= cy <= b[3]:
            return body
    if not flb_regions:
        return None
    if log is not None:
        log("  警告: 锚点(%.3f,%.3f)不落在任何 FLB 体包围盒内, "
            "已兜底取第 1 个 FLB 体——请核对是否切错板。" % (cx, cy))
    return flb_regions[0][0]


def _promote_body(work_part, comp, feat_name, log, body_index=None):
    """组件实体 → 提升体(工作部件所有, 可直接作布尔工具)。

    body_index: None=全部实体(返回列表), 0/1=第几个实体(返回单体或 None)。
    v1.8: 逐实体容错——单个实体提升失败(如不在引用集)只跳过并记日志,
    不再让整件失败(主进胶 7 实体一案: 一个坏实体毁掉全部)。
    """
    import NXOpen.Features

    proto = comp.Prototype
    bodies = _iter(proto.Bodies)
    if not bodies:
        log("  提升失败: %s 内无实体。" % proto.Name)
        return None
    if body_index is not None:
        if body_index >= len(bodies):
            log("  提升失败: 件内只有 %d 个实体, 无第 %d 个。"
                % (len(bodies), body_index + 1))
            return None
        bodies = [bodies[body_index]]
    out = []
    for bd in bodies:
        try:
            occ = comp.FindOccurrence(bd)
            if occ is None:
                log("  提升跳过一个实体: 不在组件引用集内。")
                continue
            pb = work_part.Features.CreatePromotionBuilder(
                NXOpen.Features.Promotion.Null)
            try:
                pb.Associative = False
                pb.Body.Add(occ)
                feat = pb.CommitFeature()
            finally:
                try:
                    pb.Destroy()
                except Exception:
                    pass
            try:
                feat.SetName(feat_name if len(bodies) == 1
                             else "%s_%d" % (feat_name, len(out) + 1))
            except Exception:
                pass
            registry.add(feat)
            bs = _bodies_of(feat)
            if bs:
                out.append(bs[0])
        except Exception as ex:
            log("  提升实体失败(跳过该实体): %s" % ex)
            continue
    if body_index is not None:
        return out[0] if out else None
    return out


def _bool_one(work_part, fn, target, tool, retain_tools):
    """单工具布尔, 返回特征列表或 None(失败)。"""
    try:
        r = getattr(work_part.Features, fn)(target, False, [tool],
                                            retain_tools, False)
    except TypeError:
        try:
            r = getattr(work_part.Features, fn)(target, False, [tool],
                                                retain_tools, False, False, False)
        except Exception:
            return None
    except Exception:
        return None
    if isinstance(r, tuple):
        r = r[0]
    try:
        return [f for f in r]
    except TypeError:
        return [r]


def _bool_feature(work_part, op, target, tools, name, log, retain_tools=False):
    """布尔特征(CreateSubtractFeature/CreateUniteFeature)。

    retain_tools=True 保留工具体(切槽保件, 同期刊 CopyTools)。
    v1.9 逐工具容错: 多工具合并调用失败时逐个重试, 零相交的坏工具记日志
    跳过, 不再毁掉整次布尔(垫片第1实体零相交一案)。
    """
    fn = "CreateUniteFeature" if op == "unite" else "CreateSubtractFeature"
    tools = [t for t in tools if t is not None]
    if not tools:
        return []
    feats = None
    if len(tools) == 1:
        feats = _bool_one(work_part, fn, target, tools[0], retain_tools)
    else:
        # 多工具: 先合并试一次, 失败则逐个来
        try:
            r = getattr(work_part.Features, fn)(target, False, list(tools),
                                                retain_tools, False)
            if isinstance(r, tuple):
                r = r[0]
            feats = list(r)
        except TypeError:
            try:
                r = getattr(work_part.Features, fn)(target, False, list(tools),
                                                    retain_tools, False, False, False)
                if isinstance(r, tuple):
                    r = r[0]
                feats = list(r)
            except Exception:
                feats = None
        except Exception:
            feats = None
    if not feats:
        # 逐工具: 每个单独试, 失败(如零相交)跳过并记日志
        feats = []
        for t in tools:
            fs = _bool_one(work_part, fn, target, t, retain_tools)
            if fs:
                feats.extend(fs)
            else:
                log("  布尔工具跳过(与目标无交集或失败): %s"
                    % str(getattr(t, "Name", t)))
        if not feats:
            return []
    for i, f in enumerate(feats):
        try:
            f.SetName(name or ("%sBOOL_%d" % (FEATURE_PREFIX, i)))
        except Exception:
            pass
        registry.add(f)
    return feats


def _remove_parameters(session, work_part, bodies, log):
    """阶段 8: 移除全部产物参数(用户确认: 执行后只要实体)。

    先给每个体打 MARK_ATTR 标记(与曲线同款), 再 RemoveParameters 去特征树;
    标记是重跑清理的依据(特征没了, nx_purge 按标记识别哑体)。着色在移除
    前完成(颜色保留)。失败记日志保留特征树, 不影响产物。
    """
    ok_bodies = []
    for b in bodies:
        try:
            b.SetAttribute(MARK_ATTR, SCRIPT_VERSION)
            ok_bodies.append(b)
        except Exception:
            pass                       # 已被布尔消费/失效的体, 跳过
    if not ok_bodies:
        return 0
    bld = None
    try:
        bld = work_part.Features.CreateRemoveParametersBuilder()
        for b in ok_bodies:
            try:
                bld.Objects.Add(b)
            except Exception:
                pass
        bld.Commit()
    except Exception as ex:
        log("【移除参数】失败(特征树保留): %s" % ex)
        return 0
    finally:
        if bld is not None:          # Commit 抛异常也要销毁 builder(v1.35)
            try:
                bld.Destroy()
            except Exception:
                pass
    registry.clear()                  # 特征已无, 登记表清空
    log("【移除参数】完成: %d 个实体已去参数化(重跑按标记清理)。" % len(ok_bodies))
    return len(ok_bodies)


def _usable_parts(rules, log):
    """(v1.30) 过滤出已配置参考点的可用规则; 未配置的收集并写日志。"""
    unusable = _unusable_names(rules)
    usable = {f: r for f, r in rules.items() if _rule_usable(r)}
    if unusable:
        log("【标准件】提示: 以下标准件未在 nx_std_config.py 填写参考点"
            "(ref), 本次跳过: " + ", ".join(unusable)
            + "。请实测后在 config 精确文件名行中填写。")
    return usable, unusable


def place_std_parts(session, work_part, layers, flb_regions, params, std_rules, log,
                    stats=None):
    """阶段 6: 按规则放置 stdparts 标准件(独立体)并按需布尔。

    v1.8: 放置后提升件内全部实体为工作部件独立体并删除装配组件(与用户
    手工复制粘贴一致); 旋转件 XY 自动对轴; 布尔只减指定实体且刀具体保留。
    v1.9: 存活独立体登记进 stats["STD"]["bodies"](纯切割 SUBTRACT 模式
    体已删除, 不登记), 供阶段 8 移除参数统一收集。
    v1.30: 参考点=用户在 config 按文件名填写的 ref(必需;
    未填的件在 _usable_parts 过滤阶段已排除并提示)。
    """
    import NXOpen as nx
    import NXOpen.Features

    if stats is None:
        stats = {}
    std_stats = {"curves": 0, "profiles": 0, "features": 0,
                 "bodies": [], "note": ""}
    if not std_rules:
        stats["STD"] = std_stats
        return
    no_ref = []
    log("【标准件】开始: %d 个件规则。" % len(std_rules))
    ca = work_part.ComponentAssembly
    for fname in sorted(std_rules):
        rule = std_rules[fname]
        if not _rule_usable(rule):
            no_ref.append(fname)
            continue
        path = os.path.join(stdparts_dir(), fname)
        if not os.path.isfile(path):
            log("【标准件】%s: 文件缺失, 跳过。" % fname)
            continue
        if anchors_overflow([], rule):
            # 指纹护栏(空图层+半径上限≥999)先于收集——规则配错时不必先在
            # 数万实体上白白扫描一遍(v1.35)
            log("【标准件】%s: 规则指纹命中护栏(图层=%s 半径%.4g~%.4g, "
                "空图层+大半径=全图放置会卡死), 跳过。请到标准件参数页"
                "检查/恢复默认。"
                % (fname, rule["layer"] or "全部", rule["r_min"], rule["r_max"]))
            continue
        anchors = collect_circle_anchors(layers, rule)
        if not anchors:
            log("【标准件】%s: 无匹配锚点(图层=%s 半径%.4g~%.4g), 跳过。"
                % (fname, rule["layer"] or "全部", rule["r_min"], rule["r_max"]))
            continue
        if len(anchors) > STD_MAX_ANCHORS:
            log("【标准件】%s: 锚点 %d 个超过护栏 %d——规则疑似配错, "
                "跳过。请到标准件参数页检查/恢复默认。"
                % (fname, len(anchors), STD_MAX_ANCHORS))
            continue

        flip = (rule["dir"] == "-Z")
        z = _std_z(params, rule)
        stem = os.path.splitext(fname)[0]
        ref = rule.get("ref")
        ref_xy = (float(ref[0]), float(ref[1]))
        ref_z = float(ref[2])
        off = (float(rule.get("off_x", 0.0)), float(rule.get("off_y", 0.0)),
               float(rule.get("off_z", 0.0)))
        log("【标准件】%s: 参考点=配置值 XY=(%.3f,%.3f) Z=%.3f 偏移=(%.3f,%.3f,%.3f)"
            % (fname, ref_xy[0], ref_xy[1], ref_z, off[0], off[1], off[2]))
        n_ok = n_bool = n_body = 0
        for i, anch in enumerate(anchors):
            cx, cy = anch[0], anch[1]
            m3 = _matrix3x3(nx, flip)
            name = "%s%s_%d" % (COMP_PREFIX, stem, i + 1)
            try:
                # 放置公式: basePoint = 锚点 + _place_delta(锚点−R·ref+off;
                # -Z 时 ref 随姿态旋转, v1.35)
                dx, dy, dz = _place_delta((ref_xy[0], ref_xy[1], ref_z),
                                          flip, off)
                pos = nx.Point3d(cx + dx, cy + dy, z + dz)
                try:
                    comp, _ls = ca.AddComponent(path, "MODEL", name, pos, m3, -1)
                except TypeError:
                    comp = ca.AddComponent(path, "MODEL", name, pos, m3, -1, False)
                n_ok += 1
            except Exception as ex:
                log("  %s 位置 %d 放置失败: %s" % (fname, i + 1, ex))
                continue

            # 独立体: 提升件内全部实体 → 删除装配组件(与用户手工粘贴一致)
            tools_all = _promote_body(work_part, comp,
                                      "%sBODY_%s_%d" % (FEATURE_PREFIX, stem, i + 1),
                                      log, body_index=None)
            tools_all = [t for t in (tools_all or []) if t is not None]
            n_body += len(tools_all)
            try:
                session.UpdateManager.AddToDeleteList([comp])
                session.UpdateManager.DoUpdate(
                    session.SetUndoMark(nx.Session.MarkVisibility.Invisible,
                                        "CAD3D 删组件"))
            except Exception as ex:
                log("  %s 位置 %d 组件删除失败(提升体不受影响): %s"
                    % (fname, i + 1, ex))

            bm = rule["bool_mode"]
            if bm in ("SUBTRACT", "PLACE_SUBTRACT", "UNITE") and tools_all:
                # v1.9: 布尔实体字段已删——件内全部实体一起当刀具(用户确认;
                # 位置对了不会有什么影响, 逐工具容错兜底零相交实体)
                target = _pick_target(flb_regions, cx, cy, log=log)
                if target is None:
                    # 无 FLB 体可布尔: 独立体按放置保留——不能走 SUBTRACT 删体
                    # 分支(否则孔没切、件也没了, v1.35 修复)
                    log("  %s 位置 %d: 无 FLB 体可布尔, 独立体保留(按放置处理)。"
                        % (fname, i + 1))
                    std_stats["bodies"].extend(tools_all)
                else:
                    op = "unite" if bm == "UNITE" else "subtract"
                    fs = _bool_feature(work_part, op, target, tools_all,
                                       "%s%s_%s_%d" % (FEATURE_PREFIX,
                                                       "UNI" if op == "unite" else "SUB",
                                                       stem, i + 1), log,
                                       retain_tools=True)  # 刀具体保留(用户确认)
                    if fs:
                        n_bool += 1
                    if bm == "SUBTRACT":
                        if fs:
                            # 纯切割模式: 布尔已生效才删残留刀具体(孔已切出)
                            try:
                                session.UpdateManager.AddToDeleteList(tools_all)
                                session.UpdateManager.DoUpdate(
                                    session.SetUndoMark(
                                        nx.Session.MarkVisibility.Invisible,
                                        "CAD3D 删多余体"))
                            except Exception:
                                pass
                        else:
                            # 布尔未生效(无交集/失败): 保留独立体防凭空消失
                            log("  %s 位置 %d: 布尔未生效, 独立体保留。"
                                % (fname, i + 1))
                            std_stats["bodies"].extend(tools_all)
                    else:
                        std_stats["bodies"].extend(tools_all)
            elif tools_all:
                std_stats["bodies"].extend(tools_all)
        log("【标准件】%s: 放置 %d 处, 独立体 %d 个%s (Z=%.4g, %s)。"
            % (fname, n_ok, n_body,
               (", 布尔 %d 处" % n_bool) if n_bool else "",
               z, rule["bool_mode"]))
    std_stats["profiles"] = len(std_stats["bodies"])
    if no_ref:
        log("【标准件】提示: %d 件未配置参考点已跳过: %s"
            % (len(no_ref), ", ".join(no_ref)))
    stats["STD"] = std_stats


# ---------------------------------------------------------------------------
# §5.6 JRT 加热条(工序依据用户期刊 journal.py 反推; 样板 3Djrttest.prt 为验收基准)
#   每条闭合链 × 板两侧: 拉伸(壁偏置+拔模, 齐平端→入侵端) → 嵌入端 G1 边倒圆
#   → 删远端 2 个倒圆面 → 保件相减切槽 → 齐平端倒圆(失败降半径) → 删远端 2 面
#   (圆顶) → 着色。
# ---------------------------------------------------------------------------

def _uf_face_data(uf, face):
    """UF.Modeling.AskFaceData → 7 元组 (type, point[3], dir[3], bbox[6], r, ratio, norm)。"""
    return uf.Modeling.AskFaceData(face.Tag)


def _find_flat_face(uf, body, z_plane, tol=0.6):
    """找法向±Z 且位于 z_plane 的平面(条端面)。

    v1.17: tol 0.05→0.6 并取容差内最近面——桥接截面的条拔模+壁偏置
    会让端面整体偏 ±offset×tan(拔模)(实测 ±0.34), 按精确 z 找不到端面
    → 该条两端直角无倒圆一案。
    """
    try:
        faces = list(body.GetFaces())
    except Exception:
        return None
    best, bd = None, None
    for f in faces:
        try:
            d = _uf_face_data(uf, f)
            if float(d[4]) < 1e-9 and abs(d[2][2]) > 0.999:
                dist = abs(d[1][2] - z_plane)
                if dist < tol and (best is None or dist < bd):
                    best, bd = f, dist
        except Exception:
            continue
    return best


def _edge_blend_end(work_part, uf, body, z_plane, radius, log, feat_name=None):
    """端面外边 G1 相切边倒圆(期刊同款规则 OuterEdgesOfFaces+LaminarEdge 与标志)。

    返回 (feature, 新增面列表); 失败返回 (None, [])。
    """
    import NXOpen
    import NXOpen.Features

    face = _find_flat_face(uf, body, z_plane)
    if face is None:
        log("  倒圆: 未找到 z=%.3f 端面" % z_plane)
        return None, []
    try:
        before = set(f.Tag for f in body.GetFaces())
    except Exception:
        before = set()

    bldr = work_part.Features.CreateEdgeBlendBuilder(NXOpen.Features.Feature.Null)
    try:
        sc = work_part.ScCollectors.CreateCollector()
        opts = _sc_rule_options(work_part)
        if opts is not None:
            try:
                rule = work_part.ScRuleFactory.CreateRuleOuterEdgesOfFaces([face], opts)
            except TypeError:
                rule = work_part.ScRuleFactory.CreateRuleOuterEdgesOfFaces([face])
            try:
                opts.Dispose()
            except Exception:
                pass
        else:
            rule = work_part.ScRuleFactory.CreateRuleOuterEdgesOfFaces([face])
        sc.ReplaceRules([rule], False)
        try:
            sc.AddEvaluationFilter(NXOpen.ScEvaluationFiltertype.LaminarEdge)
        except Exception:
            pass

        for _pn, _pv in (("Tolerance", 0.01), ("AllInstancesOption", False),
                         ("RemoveSelfIntersection", True),
                         ("PatchComplexGeometryAreas", True),
                         ("LimitFailingAreas", True)):
            try:
                setattr(bldr, _pn, _pv)
            except Exception:
                pass                          # 旧版缺该属性则跳过, 不整条崩
        try:
            bldr.ConvexConcaveY = False
            bldr.RollOverSmoothEdge = True
            bldr.RollOntoEdge = True
            bldr.MoveSharpEdge = True
            bldr.TrimmingOption = False
            bldr.OverlapOption = \
                NXOpen.Features.EdgeBlendBuilder.Overlap.AnyConvexityRollOver
            bldr.BlendOrder = \
                NXOpen.Features.EdgeBlendBuilder.OrderOfBlending.ConvexFirst
            bldr.SetbackOption = \
                NXOpen.Features.EdgeBlendBuilder.Setback.SeparateFromCorner
            bldr.BlendFaceContinuity = \
                NXOpen.Features.EdgeBlendBuilder.FaceContinuity.Tangent
        except Exception:
            pass
        bldr.AddChainset(sc, _fmt_num(radius))
        feat = bldr.CommitFeature()
        if feat_name:
            try:
                feat.SetName(feat_name)
            except Exception:
                pass
        registry.add(feat)
        try:
            new_faces = [f for f in body.GetFaces() if f.Tag not in before]
        except Exception:
            new_faces = []
        return feat, new_faces
    finally:
        try:
            bldr.Destroy()
        except Exception:
            pass


def _faces_healthy(rows):
    """(纯逻辑, 可离线测) 条体面体检: rows=(类型, 半径, bbox零维数) 列表。

    好(不异形) ⇔ 无退化碎片面。平面(bbox)必有 1 个零维(法向厚度)
    ——正常; 零维≥2 = 线/点状碎片(删面愈合残留实证)。
    型20/型23 样条面是样条墙+拔模几何下的正常产物(01.dxf 实证),
    不算异形; 倒圆翻卷由体积阈值兜底。返回 (是否健康, 问题描述)。
    """
    for ftype, r, zc in rows:
        if zc >= 2:
            return False, "退化碎片面(零维%d个)" % zc
    return True, ""


def _body_face_rows(uf, body):
    """条体全部面 → [(类型, 半径, bbox零维数), ...](体检用)。"""
    rows = []
    for f in body.GetFaces():
        try:
            d = uf.Modeling.AskFaceData(f.Tag)
            bb = d[3]
            zc = sum(1 for a, b in ((bb[0], bb[3]), (bb[1], bb[4]),
                                    (bb[2], bb[5])) if b - a <= 0.01)
            rows.append((int(d[0]), float(d[4]), zc))
        except Exception:
            continue
    return rows


def _flush_start_r(blend_r, r_min, thickness):
    """(纯逻辑, 可离线测) 齐平端倒圆起试半径 = min(边倒圆R, 条厚/2−0.05),
    不低于 r_min。

    【当前未接入流水线】v1.26 的逐R对照实验(exp_r)证伪了"2R>条厚即异形"
    这一前提(R3.7 反而产样条面、R3.9 全解析), 厚度预防式起试半径已回退,
    build_jrt 现在直接从边倒圆R 起试(靠体积/面体检网络兜底降R)。
    保留本函数+自测供后续再实验, 调用侧接入前先确认前提成立。
    """
    return max(float(r_min),
               min(float(blend_r), float(thickness) / 2.0 - 0.05))


def _dome_body_ok(rows):
    """(纯逻辑, 可离线测) 圆顶(齐平端)倒圆后体判据——jrt2.prt 六状态
    实测定案(用户制造): 异形(C/D, R3.9/3.8) ⇔ 体内残留 型20 样条拔模
    面×2(顶面倒圆未吞并侧壁); 干净(E/F, R3.7/完整体) 型20=0, 且 E 的
    型23 反而更多 → 型23 不是判据。rows=(类型, ...) 列表。
    返回 (是否合格, 问题描述)。"""
    n20 = sum(1 for row in rows if row[0] == 20)
    if n20:
        return False, "残留样条拔模面%d片(侧壁未被倒圆吞并)" % n20
    return True, ""


def _blend_ok(vol_before, vol_after):
    """(纯逻辑, 可离线测) 倒圆结果是否正常(不异形)。

    基准样板(3Djrttest)实证: 正常 G1 切链倒圆会沿侧壁全长滚过,
    丢体可达 11% —— 阈值不能定在个位数百分比。只拦【粗大异常】:
    体积<=0 或 丢体>25%(真翻卷是此量级的几十倍)。体积测不到不拦
    (保持旧行为)。
    """
    if vol_before is None or vol_after is None:
        return True                     # 测不到 → 不拦(旧行为)
    if vol_after <= 0.0:
        return False
    return vol_after >= vol_before * 0.75


def _body_volume(work_part, body):
    """体积(MeasureManager.NewMassProperties, 期刊签名 5 单位; 失败回
    None → 调用侧不拦截)。"""
    try:
        mm = work_part.MeasureManager
        unit_mm = work_part.UnitCollection.FindObject("MilliMeter")
        try:
            mp = mm.NewMassProperties([unit_mm] * 5, 0.99, [body])
            try:
                return float(mp.Volume())
            except Exception:
                return float(mp.Volume)
        except Exception:
            pass
        try:
            return float(body.Volume)
        except Exception:
            pass
    except Exception:
        pass
    return None


def _edge_blend_end_retry(session, work_part, uf, body, z_plane,
                          r0, r_min, r_step, log, feat_name, label,
                          dome=False):
    """带异形检测的端面倒圆: R 从 r0 起, 每轮先记撤销标记, 倒圆后体积
    校验(_blend_ok)+碎片体检(_faces_healthy); dome=True(齐平端)追加
    圆顶判据(_dome_body_ok: 体内残留型20样条面=异形, v1.27 定案)。
    异形/失败 → UndoToMark 撤销 → R-=r_step 重试到 r_min(用户工序)。
    返回 (feature, 新面列表, 实际用到的R); 全失败 → (None, [], r0)。"""
    import NXOpen
    r = float(r0)
    while r >= float(r_min) - 1e-9:
        mark = session.SetUndoMark(
            NXOpen.Session.MarkVisibility.Invisible, "CAD3D JRT试倒圆")
        v0 = _body_volume(work_part, body)
        try:
            feat, nf = _edge_blend_end(work_part, uf, body, z_plane, r, log,
                                       feat_name=feat_name)
        except Exception:
            feat, nf = None, []
        v1 = _body_volume(work_part, body) if feat is not None else None
        if feat is not None:
            rows_all = _body_face_rows(uf, body)
            okh, why = _faces_healthy(rows_all)
            if okh and dome:
                okh, why = _dome_body_ok(rows_all)
        if feat is not None and _blend_ok(v0, v1) and okh:
            if v0 is not None and v1 is not None and v0 > 0:
                log("  %s 倒圆R%.4g 体积%.1f→%.1f 面体检通过。"
                    % (label, r, v0, v1))
            return feat, nf, r
        if feat is not None and not _blend_ok(v0, v1):
            log("  %s 倒圆R%.4g 体积异常(%.1f→%.1f), 撤销降R重试。"
                % (label, r, v0, v1))
        elif feat is not None:
            log("  %s 倒圆R%.4g 面体检不过(%s), 撤销降R重试。" % (label, r, why))
        try:
            session.UndoToMark(mark, None)
        except Exception:
            pass
        r -= float(r_step)
    return None, [], float(r0)


def _delete_faces(work_part, faces, log, feat_name=None):
    """同步建模删除面(期刊 DeleteFaceBuilder Type=Face, 删除后自动愈合)。"""
    import NXOpen
    import NXOpen.Features

    faces = [f for f in faces if f is not None]
    if not faces:
        return None
    bldr = work_part.Features.CreateDeleteFaceBuilder(NXOpen.Features.Feature.Null)
    try:
        bldr.Type = NXOpen.Features.DeleteFaceBuilder.SelectTypes.Face
        opts = _sc_rule_options(work_part)
        if opts is not None:
            try:
                rule = work_part.ScRuleFactory.CreateRuleFaceDumb(list(faces), opts)
            except TypeError:
                rule = work_part.ScRuleFactory.CreateRuleFaceDumb(list(faces))
            try:
                opts.Dispose()
            except Exception:
                pass
        else:
            rule = work_part.ScRuleFactory.CreateRuleFaceDumb(list(faces))
        bldr.FaceCollector.ReplaceRules([rule], False)
        feat = bldr.Commit()
        if feat_name:
            try:
                feat.SetName(feat_name)
            except Exception:
                pass
        registry.add(feat)
        return feat
    finally:
        try:
            bldr.Destroy()
        except Exception:
            pass


def _delete_faces_safe(session, work_part, uf, body, faces, log,
                       feat_name, label):
    """带体检的删面: 整组删→体检(样条面/碎片=愈合失败)→撤销;
    逐片删→体检→撤销; 都失败保留倒圆面(宁可端部多两片圆角,
    也不出货变形条——出线端删面一案)。返回 是否有删动。"""
    import NXOpen
    faces = [f for f in faces if f is not None]
    if not faces:
        return False
    # 删面健康基线: 碎片面 + 型20样条面计数(愈合产生新样条补丁=毁容,
    # 01.dxf 圆顶删面一案; 嵌入端合法的 2 片拔模样条面以"不增加"保护)
    pre20 = sum(1 for t, _r, _z in _body_face_rows(uf, body) if t == 20)

    def _del_ok():
        rows = _body_face_rows(uf, body)
        okh, why = _faces_healthy(rows)
        if not okh:
            return False, why
        n20 = sum(1 for t, _r, _z in rows if t == 20)
        if n20 > pre20:
            return False, "样条补丁面+%d" % (n20 - pre20)
        return True, ""

    mark = session.SetUndoMark(NXOpen.Session.MarkVisibility.Invisible,
                               "CAD3D 删面试删")
    try:
        _delete_faces(work_part, faces, log, feat_name=feat_name)
    except Exception as ex:
        # NX 自身拒绝(如"剩余面无法封闭删除区域")→ 转单片回退
        log("  %s 整组删被 NX 拒绝(%s), 转单片试删。" % (label, ex))
    else:
        okh, why = _del_ok()
        if okh:
            return True
        log("  %s 整组删面后出现%s, 撤销转单片试删。" % (label, why))
    try:
        session.UndoToMark(mark, None)
    except Exception:
        pass
    # 逐片删(两片一起删愈合失败时, 单片可能愈合干净)
    done = False
    for f in faces:
        mark2 = session.SetUndoMark(NXOpen.Session.MarkVisibility.Invisible,
                                    "CAD3D 删面试删单片")
        try:
            _delete_faces(work_part, [f], log, feat_name=feat_name)
        except Exception:
            try:
                session.UndoToMark(mark2, None)
            except Exception:
                pass
            continue
        okh2, why2 = _del_ok()
        if okh2:
            done = True
        else:
            log("  %s 单片删后出现%s, 撤销该片。" % (label, why2))
            try:
                session.UndoToMark(mark2, None)
            except Exception:
                pass
    if done:
        log("  %s 整组删面愈合失败, 已改单片删(部分保留)。" % label)
        return True
    log("  %s 删面愈合均产生碎片/样条补丁, 已全部撤销——保留倒圆面。"
        % label)
    return False


def _chain_outlet_mids(chain, ents):
    """(纯逻辑, 可离线测) 出线口线中点——链上的短线段(≤15mm)且链序
    前后两邻都是线(两出线口环形通道的 8mm 口线一案; 期刊删除面正位于
    口线中点处)。跨接线(邻有弧)不在此列。"""
    mids = []
    for k, (i, _r) in enumerate(chain):
        e = ents[i]
        if e.kind != "line":
            continue
        L = math.hypot(e.p2[0] - e.p1[0], e.p2[1] - e.p1[1])
        if L > 15.0:
            continue
        pa = ents[chain[(k - 1) % len(chain)][0]]
        pb = ents[chain[(k + 1) % len(chain)][0]]
        if pa.kind == "line" and pb.kind == "line":
            mids.append(((e.p1[0] + e.p2[0]) / 2.0,
                         (e.p1[1] + e.p2[1]) / 2.0))
    return mids


def _chain_connectors(chain, ents, ratio=0.3):
    """链中的收口连接线(内外轮廓环之间的短直线) → [(中点X, 中点Y), ...]。

    期刊实测: 删面位置 = 两条连接线旁的倒圆面(面中心距连接线中点≈1)。
    判定: 最短的 2 条直线, 且长度 < ratio×其余直线中位长度。
    """
    lines = []
    for k, (i, _r) in enumerate(chain):
        e = ents[i]
        if e.kind != "line":
            continue
        L = math.hypot(e.p2[0] - e.p1[0], e.p2[1] - e.p1[1])
        # 相邻段(链序前后各一, 环回)
        pa = ents[chain[(k - 1) % len(chain)][0]]
        pb = ents[chain[(k + 1) % len(chain)][0]]
        two_lines = pa.kind == "line" and pb.kind == "line"
        lines.append((L, (e.p1[0] + e.p2[0]) / 2.0,
                      (e.p1[1] + e.p2[1]) / 2.0,
                      not two_lines))
    if len(lines) < 3:
        return []
    srt = sorted(lines, key=lambda t: t[0])
    rest = [t[0] for t in srt[2:]]
    med = sorted(rest)[len(rest) // 2]
    if srt[0][0] < ratio * med and srt[1][0] < ratio * med:
        return [(srt[0][1], srt[0][2]), (srt[1][1], srt[1][2])]
    # 泛化(01.dxf 两出线口环形通道一案): 跨接线=短直线(≤15mm, 通道
    # 宽度量级)且至少一侧邻是弧且不处于 线-线-线 连续段(8mm 口线
    # 两侧邻都是线 → 排除; 6.09 跨接线 [弧,线] → 命中)
    cands = [(t[1], t[2]) for t in lines
             if t[0] <= 15.0 and t[3]]
    if 2 <= len(cands) <= 8:
        return cands
    return []


def _conn_face_pick(face_rows, conn_mids, r_ref):
    """(纯逻辑, 可离线测) 从面行 (tag, cx, cy, 半径) 中为每个连接线中点
    挑删面。只认【圆柱面且半径≈倒圆R】的倒圆面; 距离门控
    2.5×R+2(期刊实测面中心距连接线中点≈1)——任一连接线找不到可信面
    即整组放弃(删错面会毁掉整根条, 宁可不删)。返回 [tag,...] 或 None。"""
    r_ref = float(r_ref or 0.0)
    tol_r = max(0.3, 0.25 * r_ref) if r_ref > 1e-9 else 1e18
    gate = 2.5 * max(r_ref, 1.0) + 2.0
    pool = [r for r in face_rows
            if r[3] > 1e-9 and abs(r[3] - r_ref) <= tol_r]
    picks, used = [], set()
    for (mx, my) in conn_mids:
        best, bd = None, None
        for row in pool:
            if row[0] in used:
                continue
            d = math.hypot(row[1] - mx, row[2] - my)
            if best is None or d < bd:
                best, bd = row, d
        if best is None or bd > gate:
            return None
        picks.append(best[0])
        used.add(best[0])
    return picks


def _pick_conn_faces(uf, faces, conn_mids, r_ref=None, log=None):
    """每个收口连接线中点各取最近的 1 个倒圆面(删面对象)。

    v1.17 收紧: 只认半径≈r_ref 的圆柱倒圆面 + 距离门控; 判定不可信
    返回 [](宁可保留倒圆面也不删错面——01.prt 异形条一案)。
    """
    rows = []
    for f in faces:
        try:
            d = _uf_face_data(uf, f)
            cx = (d[3][0] + d[3][3]) / 2.0
            cy = (d[3][1] + d[3][4]) / 2.0
            rows.append((f.Tag, cx, cy, float(d[4])))
        except Exception:
            continue
    tags = _conn_face_pick(rows, conn_mids, r_ref)
    if tags is None:
        if log:
            log("  删面放弃: 连接线附近未找到半径匹配的倒圆面"
                "(r_ref=%s), 保留倒圆面。" % _fmt_num(r_ref or 0.0))
        return []
    by_tag = {f.Tag: f for f in faces}
    return [by_tag[t] for t in tags if t in by_tag]


def _chain_tips(chain, ents):
    """(纯逻辑) 链的断口端点(只出现一次的端点)。"""
    from collections import Counter
    pts = []
    for i, _r in chain:
        e = ents[i]
        pts += [e.p1, e.p2]
    cnt = Counter((round(x, 3), round(y, 3)) for x, y in pts)
    return [p for p, c in cnt.items() if c == 1]


def _cluster_tips(tips, tol):
    """(纯逻辑) 断点按 ≤tol 聚类 → [[点,...], ...]。"""
    clusters = []
    for p in tips:
        for c in clusters:
            if any(math.hypot(p[0] - q[0], p[1] - q[1]) <= tol for q in c):
                c.append(p)
                break
        else:
            clusters.append([p])
    return clusters


def _merge_open_chains(opens, ents, tol=1.0, bridge_max=1.0):
    """(纯逻辑, 可离线测) 修复开链(手动拉伸能成功而脚本判开一案):

    ①并组: 断口互相贴近(≤tol)的开链并成一组(123.dxf 实测 0.24mm 接缝,
      链容差 0.01 没并上);
    ②闭合判定: 组内断点聚类(≤tol)后——
        无断点 → 已闭合, 计入闭链;
        簇形态可闭合 ⇔ 无 >2 点簇 且 单点簇恰 0 个 且 每簇缝隙≤bridge_max:
            双点簇 = 接缝缝隙(0.24mm 级) → 每簇一条桥接线;
            大缺口(缺整条边, 25mm 级)【不桥】——直线桥会横穿其它轮廓
            包出数倍体积的怪条/无效截面(实测一案), 放弃并记断口坐标,
            由用户在 2D 补线(手动拉伸同样需要先补)。
    返回 (closed_extra, bridge_jobs, open_logs):
      closed_extra = [(i, False), ...] 形链
      bridge_jobs  = [(链, [(端1, 端2, 缺口长), ...]), ...]
      open_logs    = [(段数, 断口点...), ...]
    """
    groups = [[[tuple(it) for it in o]] for o in opens]
    changed = True
    while changed:
        changed = False
        for a in range(len(groups)):
            for b in range(a + 1, len(groups)):
                ta = []
                for ch in groups[a]:
                    ta += _chain_tips([(i, False) for i, _r in ch], ents)
                tb = []
                for ch in groups[b]:
                    tb += _chain_tips([(i, False) for i, _r in ch], ents)
                if any(math.hypot(p[0] - q[0], p[1] - q[1]) <= tol
                       for p in ta for q in tb):
                    groups[a] += groups[b]
                    del groups[b]
                    changed = True
                    break
            if changed:
                break
    closed_extra, bridge_jobs, open_logs = [], [], []
    for g in groups:
        flat = [it for ch in g for it in ch]
        tips = _chain_tips([(i, False) for i, _r in flat], ents)
        if not tips:
            closed_extra.append(flat)
            continue
        clusters = _cluster_tips(tips, tol)
        singles = [c for c in clusters if len(c) == 1]
        twins = [c for c in clusters if len(c) == 2]
        bad = [c for c in clusters if len(c) > 2]
        pairs = []
        if bad or singles:
            # 断口形态不可闭合(3+点簇 / 存在单点簇=缺边级大缺口)
            open_logs.append((len(flat), tips))
            continue
        for c in twins:                       # 仅小缝(≤bridge_max)桥接
            p, q = c[0], c[1]
            gap = math.hypot(p[0] - q[0], p[1] - q[1])
            if gap > bridge_max:
                open_logs.append((len(flat), tips))
                pairs = None
                break
            pairs.append((p, q, gap))
        if pairs is None:
            continue
        bridge_jobs.append((flat, pairs))
    return closed_extra, bridge_jobs, open_logs


def _jrt_sides(z_start, z_end, bottom):
    """加热条两侧区间: 顶侧=(start,end); 底侧=底面镜像(入侵量=end-start)。

    (与期刊"镜像到板另一侧"工序等效: 两侧对称。)
    """
    intr = z_end - z_start                      # 顶侧入侵量(带方向)
    return [("T", z_start, z_end), ("B", bottom, bottom - intr)]


def _set_display(session, objs, color, translucency):
    """对象显示修改(颜色+透明度, 期刊 DisplayModification 同款)。"""
    if not objs:
        return
    dm = None
    try:
        dm = session.DisplayManager.NewDisplayModification()
        dm.ApplyToAllFaces = True
        dm.ApplyToOwningParts = False
        dm.NewColor = int(color)
        dm.NewTranslucency = int(translucency)
        dm.Apply(list(objs))
    except Exception:
        pass
    finally:
        if dm is not None:           # Apply 抛异常也要释放(v1.35)
            try:
                dm.Dispose()
            except Exception:
                pass


def build_jrt(session, work_part, layers, nx_curves, flb_regions, params, jp,
              log, stats):
    """阶段 7: JRT 加热条建模(两侧对称直建, 等效期刊的 镜像→切槽→删镜像→再镜像)。"""
    import NXOpen
    import NXOpen.Features
    import NXOpen.UF

    stats["JRT"] = {"curves": len(layers.get("JRT") or []), "profiles": 0,
                    "features": 0, "bodies": [], "note": ""}
    z_start = float(jp.get("start", 0.0))
    z_end = float(jp.get("end", 0.0))
    log("【JRT】生效参数: 起始=%.4g 结束=%.4g 边倒圆R=%.4g 步长=%.4g R下限=%.4g"
        % (z_start, z_end, jp.get("blend_r", 3.9), jp.get("r_step", 0.1),
           jp.get("r_min", 3.7)))
    if abs(z_end - z_start) <= 1e-9:
        stats["JRT"]["note"] = "起始=结束, 停用"
        log("【JRT】起始=结束(零宽度), 停用。")
        return []
    ents = layers.get("JRT") or []
    if not ents:
        stats["JRT"]["note"] = "图层无曲线"
        log("【JRT】图层无曲线, 跳过。")
        return []
    closed, opens = find_chains(ents)
    bridge_map = {}
    if opens:
        # 开链修复(手动拉伸能成功而脚本判开一案): 断口贴近的链先合并,
        # 仍有 2 断口的画桥接线闭合(桥接线打标记, 重跑清理)。
        c_extra, b_jobs, o_logs = _merge_open_chains(opens, ents)
        closed = list(closed) + c_extra
        for _chain, pairs in b_jobs:
            bridge_map[id(_chain)] = pairs
            closed.append(_chain)          # 桥接链也进建模清单
            for p1, p2, gap in pairs:
                log("【JRT】开口链(%d 段)缺口 %.3f mm, 将自动桥接闭合。"
                    % (len(_chain), gap))
        for nseg, tips in o_logs:
            log("【JRT】警告: 开链 %d 段无法自动闭合(断口 %s), 跳过——"
                "请检查 2D 图 JRT 轮廓。" % (nseg, tips))
        if not c_extra and not b_jobs:
            log("【JRT】警告: %d 条开口链未参与建模。" % len(opens))
    if not closed:
        stats["JRT"]["note"] = "无封闭链"
        log("【JRT】无封闭链(需 jrt_runner 完整流程输出), 跳过。")
        return []
    if not flb_regions:
        stats["JRT"]["note"] = "无 FLB 基准体"
        log("【JRT】无 FLB 基准体, 跳过。")
        return []

    uf = NXOpen.UF.UFSession.GetUFSession()
    s, e = params.get(TARGET_CODE, (0.0, 0.0))
    top, bottom = max(s, e), min(s, e)
    offset = float(jp.get("offset", DEFAULT_JRT["offset"]))
    draft = float(jp.get("draft", DEFAULT_JRT["draft"]))
    if draft <= 1e-9:
        draft = None                      # 0 拔模不传(与不设拔模等价)

    strips = []
    for ci, chain in enumerate(closed):
        idxs = [i for i, _r in chain]
        curves = [nx_curves["JRT"][i] for i in idxs]
        if any(c is None for c in curves):
            log("【JRT】链 %d 含创建失败曲线, 跳过。" % (ci + 1))
            continue
        br = bridge_map.get(id(chain))
        if br:
            try:
                for p1, p2, _gap in br:
                    bridge_line = work_part.Curves.CreateLine(
                        NXOpen.Point3d(p1[0], p1[1], 0.0),
                        NXOpen.Point3d(p2[0], p2[1], 0.0))
                    _mark_curve(bridge_line)
                    curves.append(bridge_line)
            except Exception as ex:
                log("【JRT】链 %d 桥接线创建失败: %s" % (ci + 1, ex))
                continue
        # 链几何中心(XY)与 help 点
        pts = []
        for i in idxs:
            ent = ents[i]
            pts.append(ent.p1 if ent.kind != "circle" else ent.c)
        cx = sum(p[0] for p in pts) / len(pts)
        cy = sum(p[1] for p in pts) / len(pts)
        first = ents[idxs[0]]
        hp = NXOpen.Point3d(first.p1[0] if first.kind != "circle" else first.c[0],
                            first.p1[1] if first.kind != "circle" else first.c[1], 0.0)
        # 删面参考点 = 收口连接线中点(期刊同位置); 未识别时回退链信息
        conns = _chain_connectors(chain, ents)
        if not conns:
            log("【JRT】链 %d 未识别收口连接线, 删面锚点改用出线口线中点。"
                % (ci + 1))

        for side, z_flush, z_embed in _jrt_sides(z_start, z_end, bottom):
            base = "%sJRT_%d%s" % (FEATURE_PREFIX, ci + 1, side)
            zlo, zhi = min(z_flush, z_embed), max(z_flush, z_embed)
            # 壁偏置方向: 齐平端 0 / 嵌入端 offset(期刊同款; 沿 +Z 起点=低 Z 端)
            off = (offset, 0.0) if z_flush > z_embed else (0.0, offset)
            try:
                feat = extrude_curves(work_part, curves, zlo, zhi, base,
                                      help_pt=hp, offset=off, draft=draft)
                stats["JRT"]["features"] += 1
            except Exception as ex:
                log("【JRT】链 %d 侧 %s 拉伸失败: %s" % (ci + 1, side, ex))
                continue
            bodies = _bodies_of(feat)
            if not bodies:
                log("【JRT】链 %d 侧 %s 无实体, 跳过。" % (ci + 1, side))
                continue
            body = bodies[0]

            # 1) 嵌入端 G1 边倒圆(异形检测+撤销降R重试到 R下限)
            r_min_all = float(jp.get("r_min", 3.7))
            try:
                _f, new_faces, _r_used = _edge_blend_end_retry(
                    session, work_part, uf, body, z_embed,
                    float(jp["blend_r"]), r_min_all,
                    max(float(jp.get("r_step", 0.1)), 1e-6), log,
                    base + "_BLE", "链%d侧%s嵌入端" % (ci + 1, side))
                if _f is not None:
                    stats["JRT"]["features"] += 1
                    # 2) 删出线端倒圆面(锚点=出线口线, 跨接线回退;
                    #    半径匹配+距离门控+体检撤销)
                    _dm = _chain_outlet_mids(chain, ents) or conns
                    if _dm and len(new_faces) > 2:
                        if _delete_faces_safe(session, work_part, uf, body,
                                              _pick_conn_faces(uf, new_faces,
                                                               _dm,
                                                               r_ref=_r_used,
                                                               log=log),
                                              log, base + "_DELE",
                                              "链%d侧%s嵌入端删面" % (ci + 1, side)):
                            stats["JRT"]["features"] += 1
            except Exception as ex:
                log("【JRT】链 %d 侧 %s 嵌入端倒圆失败: %s" % (ci + 1, side, ex))

            # 3) 保件相减切槽(槽形含嵌入端圆角)
            target = _pick_target(flb_regions, cx, cy, log=log)
            if target is not None:
                try:
                    _bool_feature(work_part, "subtract", target, [body],
                                  base + "_SUB", log, retain_tools=True)
                    stats["JRT"]["features"] += 1
                except Exception as ex:
                    log("【JRT】链 %d 侧 %s 相减失败: %s" % (ci + 1, side, ex))

            # 4) 齐平端倒圆——起试半径直接用边倒圆R(jp["blend_r"])。
            #    v1.26 曾改按条厚预防式起试(min(R, 条厚/2−0.05)), 但逐R
            #    对照实验证伪了"2R>条厚即异形"的前提并回退(见 _flush_start_r
            #    注释, 该函数保留未接入)。异形改由体检(_faces_healthy /
            #    _dome_body_ok) + 体积网(_blend_ok)检出后降 R 重试。
            _r_start = float(jp["blend_r"])
            try:
                _f2, nf2, used = _edge_blend_end_retry(
                    session, work_part, uf, body, z_flush,
                    _r_start, r_min_all,
                    max(float(jp.get("r_step", 0.1)), 1e-6), log,
                    base + "_BLF", "链%d侧%s齐平端" % (ci + 1, side),
                    dome=True)
                if _f2 is not None:
                    stats["JRT"]["features"] += 1
                    if abs(used - _r_start) > 1e-9:
                        log("【JRT】链 %d 侧 %s 齐平端倒圆降半径至 %.4g。"
                            % (ci + 1, side, used))
                else:
                    log("【JRT】链 %d 侧 %s 齐平端倒圆全部失败(下限 %.4g), "
                        "触发兜底: 回退到出线端删面完成状态(此端保留直角)。"
                        % (ci + 1, side, r_min_all))
            except Exception as ex:
                log("【JRT】链 %d 侧 %s 齐平端倒圆异常: %s" % (ci + 1, side, ex))
                used, nf2 = _r_start, []
            # 5) 删出线端倒圆面(圆顶; 锚点=出线口线, 跨接线回退)
            _dm = _chain_outlet_mids(chain, ents) or conns
            if _dm and len(nf2) > 2:
                try:
                    if _delete_faces_safe(session, work_part, uf, body,
                                          _pick_conn_faces(uf, nf2, _dm,
                                                           r_ref=used, log=log),
                                          log, base + "_DELF",
                                          "链%d侧%s圆顶删面" % (ci + 1, side)):
                        stats["JRT"]["features"] += 1
                except Exception as ex:
                    log("【JRT】链 %d 侧 %s 圆顶删面失败: %s" % (ci + 1, side, ex))

            strips.append(body)
            stats["JRT"]["profiles"] += 1

    # 6) 着色: 加热条 / 模型
    _set_display(session, strips, jp.get("color_strip", 186), jp.get("translucency", 50))
    model_bodies = []
    seen = set(id(b) for b in strips)
    for body, _b in flb_regions:
        if id(body) not in seen:
            model_bodies.append(body)
            seen.add(id(body))
    for code in LAYER_CODES:
        for body in (stats.get(code, {}).get("bodies") or []):
            if id(body) not in seen:
                model_bodies.append(body)
                seen.add(id(body))
    _set_display(session, model_bodies, jp.get("color_model", 78),
                 jp.get("translucency", 50))

    stats["JRT"]["bodies"] = strips
    log("【JRT】完成: %d 条链 × 两侧 = %d 根加热条, 特征 %d 个。"
        % (len(closed), len(strips), stats["JRT"]["features"]))
    return strips


def run_pipeline(dxf_path, params, session=None, work_part=None, log=None,
                 std_rules=None, jrt=None):
    """主流水线: 清理 → 建曲线 → 分层拉伸/布尔。返回 (ok, stats)。

    (P0) 不再 `global NXOpen` 赋值: 此前靠它给 nx_purge 供 NXOpen 引用——
    跨模块隐式全局依赖, 拆分后必断链; 现改为把 _nx 显式传给 nx_purge(nx=_nx)。
    """
    import NXOpen as _nx
    import NXOpen.Features             # 子模块显式导入(交互期刊不会自动挂包属性)
    import NXOpen.GeometricUtilities

    if session is None:
        session = _nx.Session.GetSession()
    if work_part is None:
        work_part = session.Parts.Work
    if log is None:
        log = Log(session)
    stats = {}

    log("")
    log("================ NX 分层拉伸 v%s ================" % SCRIPT_VERSION)
    # (P0) 经 notes() 取快照; 循环变量不用 _note——它会遮蔽入队函数 _note(msg)
    for _n in notes():
        log("【配置提示】%s" % _n)
    log("【输入】DXF: %s" % dxf_path)
    if not dxf_path or not os.path.isfile(dxf_path):
        log("【错误】未找到 DXF 文件, 中止。")
        return False, stats

    mark = session.SetUndoMark(_nx.Session.MarkVisibility.Visible, "CAD3D 分层拉伸")
    try:
        # 1. 解析 DXF(先于清理: 无标记曲线的迁移匹配需要本轮几何指纹)
        layers, dstats = parse_dxf(dxf_path)
        if dstats["ref_layers"]:
            log("【解析】参考图层(导入不建模): %s" % ", ".join(
                "%s×%d" % kv for kv in sorted(dstats["ref_layers"].items())))
        if dstats["unsupported"]:
            _uns = ", ".join("%s×%d" % kv
                             for kv in sorted(dstats["unsupported"].items()))
            log("【解析】警告: 不支持的实体类型已跳过: %s" % _uns)
            if dstats.get("unsupported_model"):
                # 建模图层上有丢不出的几何 → 日志+弹窗双通道, 不静默(v1.35)
                log("【警告】建模图层上有 %d 个不支持的实体(多为 LWPOLYLINE"
                    "多段线), 对应轮廓不会建模——请在 AutoCAD 用 EXPLODE "
                    "炸开成直线/圆弧后重试。" % dstats["unsupported_model"])
                try:
                    _nx.UI.GetUI().NXMessageBox.Show(
                        "CAD3D 解析警告", _nx.NXMessageBox.DialogType.Warning,
                        "DXF 建模图层上有 %d 个不支持的实体(%s)。\n"
                        "对应轮廓不会建模——请回 AutoCAD 把多段线 EXPLODE "
                        "炸开成直线/圆弧后重跑。"
                        % (dstats["unsupported_model"], _uns))
                except Exception:
                    pass
        if dstats["nonplanar"]:
            log("【解析】警告: %d 个实体 Z≠0, 已按 Z=0 处理。" % dstats["nonplanar"])
        log("【解析】共 %d 个实体, 目标图层: %s" % (
            dstats["total"],
            ", ".join("%s×%d" % (c, len(layers.get(c) or [])) for c in LAYER_CODES)))

        # 2. 清理上一轮(只删带标记/指纹匹配的, 用户图形不碰)
        nx_purge(session, work_part, log, dxf_layers=layers, nx=_nx)

        # 3. 图层映射 + 类别 + 建曲线(全图导入, 建模仅针对 LAYER_TABLE 图层)
        layer_map = assign_layers(list(layers.keys()))
        ensure_categories(work_part, layer_map, log)
        nx_curves = create_curves(work_part, layers, layer_map, log)

        # 4. 分层建模: FLB 先建(target) → none → subtract
        order = [TARGET_CODE] + [r[0] for r in LAYER_TABLE if r[5] == "none"] \
                + [r[0] for r in LAYER_TABLE if r[5] == "subtract"]
        flb_regions = []
        for code in order:
            row = [r for r in LAYER_TABLE if r[0] == code][0]
            _code, zh, _num, _s, _e, role = row
            _bodies, regions = build_layer(session, work_part, code, zh, role,
                                           layers, nx_curves, params, flb_regions,
                                           log, stats)
            if code == TARGET_CODE:
                flb_regions = regions
        if not flb_regions:
            subs = ",".join(r[0] for r in LAYER_TABLE if r[5] == "subtract")
            log("【警告】FLB 基准体未生成, %s 等布尔减层的轮廓将按普通体保留。" % subs)

        # 6. 标准件放置(全部图层建模完成后)
        if std_rules is None:
            std_rules = merge_std_rules(load_state())
        if std_rules:
            usable, _unref = _usable_parts(std_rules, log)
            place_std_parts(session, work_part, layers, flb_regions, params,
                            usable, log, stats=stats)

        # 7. JRT 加热条(双侧直建: 倒圆/删面/保件相减/圆顶/着色)
        if jrt is None:
            jrt = merge_jrt(load_state())
        build_jrt(session, work_part, layers, nx_curves, flb_regions, params,
                  jrt, log, stats)

        # 8. 移除参数(着色已在 JRT 阶段完成, 颜色保留)
        bodies, seen = [], set()
        for body, _bb in flb_regions:
            if body is not None and id(body) not in seen:
                seen.add(id(body))
                bodies.append(body)
        for code in list(LAYER_CODES) + ["JRT", "STD"]:
            for body in (stats.get(code, {}).get("bodies") or []):
                if body is not None and id(body) not in seen:
                    seen.add(id(body))
                    bodies.append(body)
        _remove_parameters(session, work_part, bodies, log)

        # 9. 汇总
        nfeat = sum(v.get("features", 0) for v in stats.values())
        log("【完成】特征 %d 个。各图层: %s" % (
            nfeat, "; ".join("%s 曲线%d/轮廓%d/%s" % (
                c, stats[c]["curves"], stats[c]["profiles"], stats[c]["note"] or "OK")
                for c in list(LAYER_CODES) + ["JRT", "STD"] if c in stats)))
        _refresh_display(session, work_part, log)
        return True, stats
    except Exception as ex:
        import traceback
        log("【错误】%s" % ex)
        log("【堆栈】%s" % traceback.format_exc())
        try:
            session.UndoToMark(mark, "CAD3D 出错回滚")
            log("【回滚】已撤销本次全部改动。")
        except Exception as ex2:
            log("【回滚失败】%s" % ex2)
        try:
            _nx.UI.GetUI().NXMessageBox.Show(
                "CAD3D 分层拉伸", _nx.NXMessageBox.DialogType.Error, str(ex))
        except Exception:
            pass
        return False, stats


# ============================================================================
# §6 Block UI Styler 对话框(回调类模式同官方 ChangeFaceColor 样例)
# ============================================================================

def _dlg_show(dialog):
    """跨版本弹出 BlockStyler 对话框: NX2312 用 Launch(); NX10/11/12 无 Launch
    (实机交互报 'BlockDialog' object has no attribute 'Launch')→ 用 Show()。
    按存在性选方法(Launch→Show→ReplayDialog), 2312 恒先命中 Launch=零回归。
    返回底层方法的响应码(int; Show/Launch 语义一致)。"""
    for _m in ("Launch", "Show", "ReplayDialog"):
        _f = getattr(dialog, _m, None)
        if callable(_f):
            return _f()
    raise AttributeError("BlockDialog 无 Launch/Show/ReplayDialog 显示方法")


class SelectionDialog(object):
    """第一段"标准件选择"对话框(每件一个复选框; 取消=中止整个流程)。"""

    def __init__(self, dlx_path, files, defaults):
        import NXOpen
        import NXOpen.BlockStyler
        self.nx = NXOpen
        self.files = files
        self.defaults = set(defaults)
        self.theUI = NXOpen.UI.GetUI()
        self.theDialog = self.theUI.CreateDialog(dlx_path)
        self.theDialog.AddOkHandler(self.ok_cb)
        self.theDialog.AddCancelHandler(self.cancel_cb)
        self.theDialog.AddInitializeHandler(self.initialize_cb)
        try:
            self.theDialog.AddDialogShownHandler(self.show_cb)
        except Exception:
            pass
        self.blocks = {}
        self._shown = False
        self.result = None          # None=取消; 否则=选中文件名列表

    def show_cb(self):
        """首显后再按记忆勾选一遍(同 ParamDialog.show_cb, 防保留值覆盖)。"""
        if not getattr(self, "_shown", False):
            self._shown = True
            try:
                for i, f in enumerate(self.files):
                    b = self._find("SEL%d" % i)
                    try:
                        b.Value = (f in self.defaults)
                    except Exception:
                        pass
            except Exception:
                pass
        return 0

    def _find(self, bid):
        if bid not in self.blocks:
            b = self.theDialog.TopBlock.FindBlock(bid)
            if b is None:
                # 找不到不缓存: 缓存 None 会让该块此后永远读不到,
                # 参数静默回退(v1.35 修复)
                return None
            self.blocks[bid] = b
        return self.blocks[bid]

    def initialize_cb(self):
        for i, f in enumerate(self.files):
            try:
                b = self._find("SEL%d" % i)
                b.Label = f
                b.Value = (f in self.defaults)
            except Exception:
                pass

    def ok_cb(self):
        sel = []
        for i, f in enumerate(self.files):
            try:
                if bool(self._find("SEL%d" % i).Value):
                    sel.append(f)
            except Exception:
                pass
        self.result = sel
        return 0

    def cancel_cb(self):
        self.result = None
        return 0

    def Launch(self):
        try:
            _dlg_show(self.theDialog)
        except Exception as ex:
            self.theUI.NXMessageBox.Show(
                "CAD3D", self.nx.NXMessageBox.DialogType.Error, str(ex))
        return self.result

    def Dispose(self):
        if getattr(self, "theDialog", None) is not None:
            try:
                self.theDialog.Dispose()
            except Exception:
                pass
            self.theDialog = None


def execute_pipeline(dxf, params, jrt, std_rules, session,
                     std_rules_all=None, selected=None, ui=None,
                     jt_link_mode=None):
    """三段式最终执行: 校验 DXF → 保存 JSON(全部规则+选中清单) → run_pipeline。"""
    import NXOpen

    if not dxf or not os.path.isfile(dxf):
        dxf = resolve_dxf_path({"dxf_path": dxf})
    if not dxf or not os.path.isfile(dxf):
        if ui is None:
            ui = NXOpen.UI.GetUI()
        ui.NXMessageBox.Show(
            "CAD3D", NXOpen.NXMessageBox.DialogType.Warning,
            "未找到有效的 DXF 文件。\n请在主参数窗口顶部选择 DXF 文件,\n"
            "或把 DXF 放到脚本同目录后重试。")
        return False
    # 保存: 全部件规则合并(未选中件保留旧配置) + 选中清单
    full_rules = dict(std_rules_all or {})
    full_rules.update(std_rules or {})
    save_state(dxf, {k: list(v) for k, v in params.items()}, full_rules,
               selected=selected,
               jrt_se=[jrt.get("start", 0.0), jrt.get("end", 0.0)],
               jt_link_mode=jt_link_mode)
    ok, _stats = run_pipeline(dxf, params, session=session,
                              work_part=session.Parts.Work,
                              log=Log(session), std_rules=std_rules, jrt=jrt)
    return ok


class _BlockDialogBase(object):
    """BlockStyler 对话框公共基类: 块查找/读写辅助 + 标准件行收集。

    (三段式改造抽出: ParamDialog(窗口②) 与 StdParamsDialog(窗口③) 共用,
    改字段只改一处。)子类需设置: theDialog/std_files/std_rules。
    """

    def _find(self, bid):
        if bid not in self.blocks:
            b = self.theDialog.TopBlock.FindBlock(bid)
            if b is None:
                # 找不到不缓存: 缓存 None 会让该块此后永远读不到,
                # 参数静默回退(v1.35 修复)
                return None
            self.blocks[bid] = b
        return self.blocks[bid]

    def _set_label(self, bid, text):
        try:
            self._find(bid).Label = text
        except Exception:
            pass

    def _dbg_footprint(self, msg):
        """回调异常写调试脚印(独立文件 logs/nx_dialog_debug.txt), 不静默——
        吞错无痕迹曾致"联动坏了无从排查"(历史事故同型, v1.35)。"""
        try:
            with io.open(os.path.join(_logs_dir(), "nx_dialog_debug.txt"),
                         "a", encoding="utf-8") as f:
                f.write("[%s] %s %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"),
                                          type(self).__name__, msg))
        except Exception:
            pass

    def _get_double(self, bid, fallback):
        try:
            v = self._find(bid).Value
            return float(v) if v is not None else fallback
        except Exception:
            return fallback

    def _enum_idx_of(self, b):
        """枚举当前序号(真实 UI 值): ValueAsString 标签反查第一优先——
        它反映界面真实显示项; .Value 次之; GetProperties().GetInteger
        【末位不用】—— v1.15 实测该通道与界面脱钩(写进属性副本, 界面
        仍显示 XML 内嵌值; OK 收集时读到初始 0 → 规则全变"空图层/全
        半径", 执行时全图层海量放置卡死一案)。fallback 由调用方处理。
        """
        try:
            s = b.ValueAsString
            if s:
                return s                     # 调用方用标签时直接拿字符串
        except Exception:
            pass
        try:
            v = b.Value
            if isinstance(v, (int, float)):
                return int(v)
        except Exception:
            pass
        return -1

    def _set_enum_idx(self, bid, idx, labels=None):
        """枚举置选中序号, 逐通道尝试+读回验证(v1.18 实测定案):
        ①Value=int; ②PropertyList.SetEnum("Value", idx)——枚举属性是
        独立类型, v1.14 用 SetInteger 类型不符=写不进(恢复默认改不动
        图层/布尔/方向/Z基准一案); ③SetEnumAsString(需 labels);
        ④SetInteger 兜底。全部失败只静默(收集侧 ValueAsString 仍以
        界面真实显示为准)。"""
        try:
            b = self._find(bid)
        except Exception:
            return
        idx = int(idx)

        def ok():
            got = self._enum_idx_of(b)
            if isinstance(got, str):
                return bool(labels) and got in labels \
                    and labels.index(got) == idx
            return got == idx

        for kind in ("value", "setenum", "setenumstr", "setint"):
            props = None
            try:
                if kind == "value":
                    b.Value = idx
                elif kind == "setenum":
                    props = b.GetProperties()
                    props.SetEnum("Value", idx)
                elif kind == "setenumstr":
                    if labels:
                        props = b.GetProperties()
                        props.SetEnumAsString("Value", labels[idx])
                else:
                    props = b.GetProperties()
                    props.SetInteger("Value", idx)
            except Exception:
                pass
            finally:
                if props is not None:   # PropertyList 用完即释放(v1.35)
                    try:
                        props.Dispose()
                    except Exception:
                        pass
            if ok():
                return

    def _apply_dialog_sizing(self, log=None):
        """显示时把对话框尺寸策略设为自适应内容(宽度一案)。

        NX2312 的 dlx 块模型没有宽度属性(double/label/对话框官方全属性
        表已验证, 仅字符串块有按字符数的 Width), 对话框尺寸唯一钩子是
        TopBlock.DialogSizing(运行时才有, TopBlock 显示前为 None)。
        这里读成员表, 挑含 auto/fit/content 的项设置; 都没有就不动。
        探查结果写脚本目录 nx_dialog_debug.txt(独立脚印文件, 批量测试
        的 report.txt 不会覆盖它)——同时也是 show 回调是否触发的证据。
        """
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        info = []
        try:
            tb = self.theDialog.TopBlock
            if tb is None:
                info.append("TopBlock=None(show 未触发或对话框未就绪)")
            else:
                try:
                    members = [str(m) for m in
                               (tb.GetDialogSizingMembers() or [])]
                except Exception as ex:
                    members = []
                    info.append("成员表读失败: %r" % ex)
                try:
                    cur = str(tb.DialogSizingAsString)
                except Exception as ex:
                    cur = "读失败:%r" % ex
                pick = None
                for m in members:
                    low = m.lower()
                    if any(k in low for k in ("auto", "fit", "content")):
                        pick = m
                        break
                info.append("成员=%s 当前=%s → 选%s"
                            % (members or "空", cur, pick or "不动"))
                if pick and pick != cur:
                    try:
                        tb.DialogSizingAsString = pick
                        info.append("已设置(AsString)")
                    except Exception:
                        _pl = None
                        try:
                            _pl = tb.GetProperties()
                            _pl.SetEnum("DialogSizing", pick)
                            info.append("已设置(SetEnum)")
                        except Exception as ex:
                            info.append("设置失败: %r" % ex)
                        finally:
                            if _pl is not None:
                                try:
                                    _pl.Dispose()
                                except Exception:
                                    pass
        except Exception as ex:
            info.append("异常: %r" % ex)
        try:
            with io.open(os.path.join(_logs_dir(), "nx_dialog_debug.txt"),
                         "a", encoding="utf-8") as f:
                f.write("[%s] %s %s\n" % (stamp, type(self).__name__,
                                           "; ".join(info)))
        except IOError:
            pass
        if log:
            log("【对话框】%s" % "; ".join(info))

    def _get_enum_idx(self, bid, fallback, labels=None):
        """枚举当前序号: 真实 UI 值(_enum_idx_of, 标签反查优先) →
        labels 里定位; 都失败才用 fallback。
        (教训: 读取静默回落曾致全部下拉卡第 0 项 → 规则错乱/卡死。)"""
        b = self._find(bid)
        got = self._enum_idx_of(b)
        if isinstance(got, str):
            if labels and got in labels:
                return labels.index(got)
            return fallback
        if got >= 0:
            return got
        return fallback

    def _collect_std(self):
        """对话框标准件行 → 规则表(序号映射语义值; 枚举读取带标签反查)。"""
        rules = {}
        for i, fname in enumerate(self.std_files):
            pfx = "SP%d_" % i
            # 起底用现有规则(保留 ref 等非对话框字段), 再覆盖对话框字段
            r = dict(self.std_rules.get(fname, DEFAULT_STD_RULE))
            li = min(self._get_enum_idx(pfx + "layer", 0,
                                        [t for _v, t in LAYER_SEL_OPTS]),
                     len(LAYER_SEL_OPTS) - 1)
            r["layer"] = LAYER_SEL_OPTS[li][0]
            zi = min(self._get_enum_idx(pfx + "zmode", 0,
                                        [t for _v, t in ZMODE_OPTS]),
                     len(ZMODE_OPTS) - 1)
            r["z_mode"] = ZMODE_OPTS[zi][0]
            bi = min(self._get_enum_idx(pfx + "bool", 0,
                                        [t for _v, t in BOOL_OPTS]),
                     len(BOOL_OPTS) - 1)
            r["bool_mode"] = BOOL_OPTS[bi][0]
            di = min(self._get_enum_idx(pfx + "dir", 0,
                                        [t for _v, t in DIR_OPTS]),
                     len(DIR_OPTS) - 1)
            r["dir"] = DIR_OPTS[di][0]
            r["r_min"] = self._get_double(pfx + "rmin", r["r_min"])
            r["r_max"] = self._get_double(pfx + "rmax", r["r_max"])
            r["off_x"] = self._get_double(pfx + "offx", r["off_x"])
            r["off_y"] = self._get_double(pfx + "offy", r["off_y"])
            r["off_z"] = self._get_double(pfx + "offz", r["off_z"])
            _old_rule = self.std_rules.get(fname) or {}
            if (str(_old_rule.get("layer") or "").upper() == "CXK"
                    and r["layer"] != "CXK"):
                # CXK 行的 dlx 无半径框: 切到圆心层时旧半径值多半是
                # 0~9999 全半径——重置为保守默认并提示核对, 防海量锚点
                # (v1.35; 界面"恢复默认"仍可回到出厂族值)
                r["r_min"], r["r_max"] = 0.0, 15.0
                _note("【%s】定位图层由 CXK 改为 %s: 半径筛选此前未在"
                      "界面显示, 已重置为 0~15, 请在窗口③核对。"
                      % (fname, r["layer"]))
            rules[fname] = sanitize_std_rule(r)
        return rules


class ParamDialog(_BlockDialogBase):
    def __init__(self, dlx_path, std_rules=None, selected=None,
                 execute_on_ok=True):
        import NXOpen
        import NXOpen.BlockStyler
        self.nx = NXOpen
        self.theSession = NXOpen.Session.GetSession()
        self.theUI = NXOpen.UI.GetUI()
        self.theDialog = self.theUI.CreateDialog(dlx_path)
        self.theDialog.AddApplyHandler(self.apply_cb)
        self.theDialog.AddOkHandler(self.ok_cb)
        self.theDialog.AddUpdateHandler(self.update_cb)
        self.theDialog.AddCancelHandler(self.cancel_cb)
        self.theDialog.AddInitializeHandler(self.initialize_cb)
        # 首显回调: NX2312 实名 AddDialogShownHandler(自省实测);
        # v1.11 误写 AddShowHandler(不存在, 被吞) → 首显补填从未生效,
        # NX 会话保留值恢复后无人覆盖(R下限3.6幽灵值/固定错乱一案)。
        try:
            self.theDialog.AddDialogShownHandler(self.show_cb)
        except Exception:
            pass
        self.blocks = {}
        self.result_params = None
        self.result_dxf = None
        self.result_jrt = None
        self.result_mode = None
        self.execute_on_ok = execute_on_ok
        self.state = load_state()
        self.params = merge_params(self.state)
        # 两段式: 第一段选中的件才进参数页; 其余件的规则保留用于保存
        self.std_rules_all = merge_std_rules(self.state)
        self.std_rules = std_rules if std_rules is not None else self.std_rules_all
        self.std_files = sorted(self.std_rules.keys())
        self.selected = list(selected) if selected is not None \
            else sorted(self.std_rules.keys())
        self.jrt = jrt_with_memory(self.state, self.params)
        self.jt_mode = jt_mode_with_memory(self.state)
        self._shown = False
        self._initializing = False

    # ---------- 辅助 ----------
    def _current_jt_mode(self):
        """读 jt_link 枚举当前模式(标签优先, 序号次之; 失败回上次模式)。"""
        b = self._find("jt_link")
        if b is not None:
            try:
                s = b.ValueAsString
                if s and s in JT_LINK_MODES:
                    return s
            except Exception:
                pass
            try:
                return JT_LINK_OPTS[int(b.Value)][0]
            except Exception:
                pass
        return self.jt_mode
    def _get_path(self):
        b = self._find("dxf_file")
        try:
            return str(b.Path) or ""
        except Exception:
            try:
                pl = self.theDialog.GetBlockProperties("dxf_file")
                return str(pl.GetString("Path")) or ""
            except Exception:
                return ""

    # ---------- 回调 ----------
    def initialize_cb(self):
        """NX 初始化回调 → 统一预填(见 _prefill_all)。"""
        self._prefill_all()

    def _invalid_response(self):
        """让对话框保持打开的返回值(ok_cb/apply_cb 校验失败用)。"""
        try:
            return self.nx.BlockStyler.BlockDialog.DialogResponse.Invalid
        except Exception:
            return 1

    def _dxf_valid_or_warn(self):
        """确定/应用前校验 DXF 路径存在(用户需求); 无效弹窗且不放行。"""
        p = self._get_path()
        if p and os.path.isfile(p):
            return True
        try:
            self.theUI.NXMessageBox.Show(
                "CAD3D", self.nx.NXMessageBox.DialogType.Warning,
                "DXF 文件不存在或路径无效:\n%s\n\n请重新选择有效的 .dxf 图纸。"
                % (p or "(未选择)"))
        except Exception:
            pass
        return False

    def _prefill_all(self):
        """打开/首显统一预填全部受控块: 各层起始/结束=JSON 记忆;
        JRT 三参数恒默认(3.9/0.1/3.7), start/end=记忆或按 FLB 联动。

        _initializing 守卫: 程序化写 FLB 值若触发 update_cb, 不做联动
        覆盖——否则用户上次单独改过的 LS/RZ/DK/DP 会在打开瞬间被盖回
        联动值(记忆"不生效/错乱"的一个根因)。
        """
        self._initializing = True
        try:
            self._set_label("grp_file", "输入文件")
            self._set_label("grp_flb", DIALOG_GROUPS[0][1])
            self._set_label("grp_plain", DIALOG_GROUPS[1][1])
            self._set_label("grp_sub", DIALOG_GROUPS[2][1])
            # JT 联动模式预填(v1.37)
            try:
                self._set_enum_idx("jt_link",
                                   _opt_index(JT_LINK_OPTS, self.jt_mode),
                                   [t for _v, t in JT_LINK_OPTS])
            except Exception:
                pass
            zh = {r[0]: r[1] for r in LAYER_TABLE}
            for _gid, _t, codes in DIALOG_GROUPS:
                for code in codes:
                    self._set_label(code + "_start", "%s %s 起始距离" % (code, zh[code]))
                    self._set_label(code + "_end", "%s %s 结束距离" % (code, zh[code]))
                    s, e = self.params[code]
                    try:
                        self._find(code + "_start").Value = s
                        self._find(code + "_end").Value = e
                    except Exception:
                        pass
            try:
                self.theDialog.TopBlock.Label = "NX 分层拉伸 (DXF→3D)"
            except Exception:
                pass
            # 预填 DXF 路径
            p = self.state.get("dxf_path") or resolve_dxf_path(self.state)
            try:
                self._find("dxf_file").Path = p
            except Exception:
                pass
            # (v1.35) 删除两段式时代的 SP* 标准件行预填循环——窗口② dlx 已
            # 不含 SP* 块(标准件参数页在窗口③), 该循环只剩逐块注定失败的查找
            # 预填加热条参数(颜色/透明度固定不进界面; id 统一 "jrt_"+key)
            for key, _label in JRT_FIELDS:
                try:
                    self._find("jrt_" + key).Value = self.jrt.get(key)
                except Exception:
                    pass
        except Exception as ex:
            self.theUI.NXMessageBox.Show("CAD3D", self.nx.NXMessageBox.DialogType.Error,
                                         str(ex))
        finally:
            self._initializing = False

    def show_cb(self):
        """首次显示后再预填一遍: NX 可能在 initialize 之后恢复会话保留值
        盖掉程序化预填(JRT 三参数"要点默认按钮才恢复"的残留渠道);
        只执行一次, 不与用户后续编辑冲突。"""
        if not getattr(self, "_shown", False):
            self._shown = True
            self._prefill_all()
            self._apply_dialog_sizing()
        return 0

    def update_cb(self, block):
        """FLB 起始/结束任一变动 → 按 LINK_RULES 实时刷新 LS/RZ/DK/DP/JT
        与 JRT(联动后各层仍可单独修改; 再改 FLB 会再次覆盖);
        "JT 联动模式"切换 → 按新模式重推 JT(v1.37)。"""
        if getattr(self, "_initializing", False):
            return 0                    # 预填写值不算用户改动
        try:
            # 加热条恢复默认: 三个几何参数回 DEFAULT_JRT(3.9/0.1/3.7),
            # 起始/结束随 FLB 联动重推(与其他层的联动规则一致)
            try:
                if block is self._find("jrt_reset"):
                    s0 = self._get_double("FLB_start", 0.0)
                    e0 = self._get_double("FLB_end", 0.0)
                    jrt = dict(DEFAULT_JRT)
                    js, je = derive_linked(max(s0, e0), min(s0, e0)).get(
                        "JRT", (DEFAULT_JRT["start"], DEFAULT_JRT["end"]))
                    jrt["start"], jrt["end"] = js, je
                    for key, _label in JRT_FIELDS:
                        try:
                            self._find("jrt_" + key).Value = jrt[key]
                        except Exception:
                            pass
                    return 0
            except Exception as ex:
                self._dbg_footprint("update_cb jrt_reset 异常: %r" % ex)
            # JT 联动模式切换: 按新模式重推 JT(v1.37)
            try:
                if block is self._find("jt_link"):
                    self.jt_mode = self._current_jt_mode()
                    s0 = self._get_double("FLB_start", 0.0)
                    e0 = self._get_double("FLB_end", 0.0)
                    v1, v2 = _jt_link_values(max(s0, e0), min(s0, e0),
                                             self.jt_mode)
                    self._find("JT_start").Value = v1
                    self._find("JT_end").Value = v2
                    cs, ce = _cx_link_values(v1)
                    self._find("CX_start").Value = cs
                    self._find("CX_end").Value = ce
                    return 0
            except Exception as ex:
                self._dbg_footprint("update_cb jt_link 异常: %r" % ex)
            # CX 跟 JT(v1.38): 手改 JT 起/止 → CX 立即跟随
            try:
                if block in (self._find("JT_start"), self._find("JT_end")):
                    cs, ce = _cx_link_values(self._get_double("JT_start", 0.0))
                    self._find("CX_start").Value = cs
                    self._find("CX_end").Value = ce
                    return 0
            except Exception as ex:
                self._dbg_footprint("update_cb jt->cx 异常: %r" % ex)
            flb_s = self._find("FLB_start")
            flb_e = self._find("FLB_end")
            if block in (flb_s, flb_e):
                s = self._get_double("FLB_start", 0.0)
                e = self._get_double("FLB_end", 0.0)
                linked = derive_linked(max(s, e), min(s, e),
                                       jt_mode=self._current_jt_mode())
                for code, (v1, v2) in linked.items():
                    for suffix, val in (("_start", v1), ("_end", v2)):
                        bid = ("jrt" if code == "JRT" else code) + suffix
                        try:
                            self._find(bid).Value = val
                        except Exception:
                            pass
                # CX 跟 JT起始(v1.38 修订): 起始同 JT, 结束=起始−偏移(槽深固定)
                cs, ce = _cx_link_values(linked["JT"][0])
                try:
                    self._find("CX_start").Value = cs
                    self._find("CX_end").Value = ce
                except Exception:
                    pass
        except Exception as ex:
            self._dbg_footprint("update_cb(%r) 异常: %r"
                                % (getattr(block, "Name", block), ex))
        return 0

    def cancel_cb(self):
        # 取消=明确中止: 清掉此前 Apply 已写入的结果槽——否则 main 会在
        # 取消后仍按"已确定"继续走窗口③/执行(v1.35 修复)
        self.result_params = None
        self.result_jrt = None
        self.result_dxf = None
        self.result_mode = None
        return 0

    def _collect(self):
        params = {}
        for code in LAYER_CODES:
            d_s, d_e = self.params[code]
            s = self._get_double(code + "_start", d_s)
            e = self._get_double(code + "_end", d_e)
            params[code] = (s, e)
        # CX 恒随 JT(v1.38 设计): 采集时直接从"最终 JT"重算, 兜底旧版对话框
        # 块程序化赋值后可能不即时重绘、导致 CX_end 停在旧值(如固定 -135)。
        if "JT" in params and "CX" in params:
            params["CX"] = _cx_link_values(params["JT"][0])
        return params

    def _collect_jrt(self):
        jrt = dict(DEFAULT_JRT)          # 颜色/透明度等固定值不经对话框
        for key, _label in JRT_FIELDS:
            jrt[key] = self._get_double("jrt_" + key, jrt[key])
        return jrt

    def _execute(self):
        if not self._dxf_valid_or_warn():
            return self._invalid_response()
        params = self._collect()
        jrt = self._collect_jrt()
        dxf = self._get_path()
        if not self.execute_on_ok:
            # 窗口②: 只收集暂存, 由窗口③(或无件时 main)统一执行
            self.result_params = params
            self.result_jrt = jrt
            self.result_dxf = dxf
            self.result_mode = self._current_jt_mode()
            return 0
        std_rules = self._collect_std()
        self.params = params
        self.std_rules = std_rules
        self.jrt = jrt
        ok = execute_pipeline(dxf, params, jrt, std_rules, self.theSession,
                              std_rules_all=self.std_rules_all,
                              selected=self.selected, ui=self.theUI,
                              jt_link_mode=self._current_jt_mode())
        return 0 if ok else 1

    def apply_cb(self):
        try:
            return self._execute()
        except Exception as ex:
            self.theUI.NXMessageBox.Show("CAD3D", self.nx.NXMessageBox.DialogType.Error,
                                         str(ex))
            return 1

    def ok_cb(self):
        try:
            return self._execute()
        except Exception as ex:
            self.theUI.NXMessageBox.Show("CAD3D", self.nx.NXMessageBox.DialogType.Error,
                                         str(ex))
            return 1

    def Launch(self):
        try:
            return _dlg_show(self.theDialog)
        except Exception as ex:
            self.theUI.NXMessageBox.Show("CAD3D", self.nx.NXMessageBox.DialogType.Error,
                                         str(ex))
            return self.nx.BlockStyler.BlockDialog.DialogResponse.Cancel

    def Dispose(self):
        if getattr(self, "theDialog", None) is not None:
            try:
                self.theDialog.Dispose()
            except Exception:
                pass
            self.theDialog = None


class StdParamsDialog(_BlockDialogBase):
    """第三段"标准件参数"对话框: 每件一个可收起组, OK/Apply 执行, 取消中止。

    参数(params/jrt/dxf)来自窗口②的收集结果; 选中件规则本窗可改;
    未选中件的规则(std_rules_all)仅用于最终保存合并。
    """

    def __init__(self, dlx_path, std_rules, params, jrt, dxf, selected,
                 std_rules_all=None, jt_mode=None):
        import NXOpen
        import NXOpen.BlockStyler
        self.nx = NXOpen
        self.theSession = NXOpen.Session.GetSession()
        self.theUI = NXOpen.UI.GetUI()
        self.theDialog = self.theUI.CreateDialog(dlx_path)
        self.theDialog.AddApplyHandler(self.apply_cb)
        self.theDialog.AddOkHandler(self.ok_cb)
        self.theDialog.AddCancelHandler(self.cancel_cb)
        self.theDialog.AddUpdateHandler(self.update_cb)
        self.theDialog.AddInitializeHandler(self.initialize_cb)
        try:
            self.theDialog.AddDialogShownHandler(self.show_cb)
        except Exception:
            pass
        self.blocks = {}
        self._shown = False
        self._initializing = False
        self.std_rules = std_rules
        self.std_files = sorted(std_rules.keys())
        self.params = params
        self.jrt = jrt
        self.jt_mode = jt_mode
        self.dxf = dxf
        self.selected = list(selected) if selected is not None else self.std_files
        self.std_rules_all = std_rules_all if std_rules_all is not None \
            else dict(std_rules)

    def initialize_cb(self):
        """NX 初始化回调 → 统一预填。"""
        self._prefill_all()

    def _prefill_all(self):
        self._initializing = True
        try:
            for i, fname in enumerate(self.std_files):
                r = self.std_rules[fname]
                pfx = "SP%d_" % i
                self._set_enum_idx(pfx + "layer",
                                   _opt_index(LAYER_SEL_OPTS, r["layer"]))
                self._set_enum_idx(pfx + "zmode",
                                   _opt_index(ZMODE_OPTS, r["z_mode"]))
                self._set_enum_idx(pfx + "bool",
                                   _opt_index(BOOL_OPTS, r["bool_mode"]))
                self._set_enum_idx(pfx + "dir",
                                   _opt_index(DIR_OPTS, r["dir"]))
                for key, fld in (("rmin", "r_min"), ("rmax", "r_max"),
                                 ("offx", "off_x"),
                                 ("offy", "off_y"), ("offz", "off_z")):
                    try:
                        self._find(pfx + key).Value = r[fld]
                    except Exception:
                        pass
        except Exception as ex:
            self.theUI.NXMessageBox.Show("CAD3D", self.nx.NXMessageBox.DialogType.Error,
                                         str(ex))
        finally:
            self._initializing = False

    def show_cb(self):
        """首次显示后再预填一遍(同 ParamDialog.show_cb)。"""
        if not getattr(self, "_shown", False):
            self._shown = True
            self._prefill_all()
            self._apply_dialog_sizing()
        return 0

    def update_cb(self, block):
        """恢复默认按钮: 把该件的 9 个参数块刷回内置默认值(无默认的新件
        按钮不生成, 双保险再查一次 None → 按了也不动, 不报错)。"""
        if getattr(self, "_initializing", False):
            return 0
        try:
            for i, fname in enumerate(self.std_files):
                bid = "SP%d_reset" % i
                try:
                    if block is self._find(bid):   # 无该按钮时 FindBlock 回 None
                        self._reset_std(i)
                        break
                except Exception:
                    continue
        except Exception:
            pass
        return 0

    def _reset_std(self, i):
        """恢复默认: 内置默认表命中→表值; 未命中(新件)→通用安全默认。

        sanitize_std_rule(None) 即通用默认(全部图层/全半径/FLB顶/仅放置/
        +Z/零偏移), 两种情况统一走 sanitize。
        """
        fname = self.std_files[i]
        r = sanitize_std_rule(std_part_defaults(fname))
        self.std_rules[fname] = r
        pfx = "SP%d_" % i
        self._set_enum_idx(pfx + "layer",
                           _opt_index(LAYER_SEL_OPTS, r["layer"]),
                           [t for _v, t in LAYER_SEL_OPTS])
        self._set_enum_idx(pfx + "zmode",
                           _opt_index(ZMODE_OPTS, r["z_mode"]),
                           [t for _v, t in ZMODE_OPTS])
        self._set_enum_idx(pfx + "bool",
                           _opt_index(BOOL_OPTS, r["bool_mode"]),
                           [t for _v, t in BOOL_OPTS])
        self._set_enum_idx(pfx + "dir",
                           _opt_index(DIR_OPTS, r["dir"]),
                           [t for _v, t in DIR_OPTS])
        for key, fld in (("rmin", "r_min"), ("rmax", "r_max"),
                         ("offx", "off_x"),
                         ("offy", "off_y"), ("offz", "off_z")):
            try:
                self._find(pfx + key).Value = r[fld]
            except Exception:
                pass
        try:
            self._set_label(pfx + "zval",
                            "Z基准值: %.4g" % _std_z(self.params, r))
        except Exception:
            pass

    def cancel_cb(self):
        return 0

    def _execute(self):
        try:
            rules = self._collect_std()
            ok = execute_pipeline(self.dxf, self.params, self.jrt, rules,
                                  self.theSession,
                                  std_rules_all=self.std_rules_all,
                                  selected=self.selected, ui=self.theUI,
                                  jt_link_mode=self.jt_mode)
            return 0 if ok else 1
        except Exception as ex:
            self.theUI.NXMessageBox.Show("CAD3D", self.nx.NXMessageBox.DialogType.Error,
                                         str(ex))
            return 1

    def apply_cb(self):
        return self._execute()

    def ok_cb(self):
        return self._execute()

    def Launch(self):
        try:
            return _dlg_show(self.theDialog)
        except Exception as ex:
            self.theUI.NXMessageBox.Show("CAD3D", self.nx.NXMessageBox.DialogType.Error,
                                         str(ex))
            return self.nx.BlockStyler.BlockDialog.DialogResponse.Cancel

    def Dispose(self):
        if getattr(self, "theDialog", None) is not None:
            try:
                self.theDialog.Dispose()
            except Exception:
                pass
            self.theDialog = None


# ============================================================================
# §7 自测 / 合成 DXF / 批量模式 / 入口
# ============================================================================

# nx_selftest: 自测 / 合成 DXF / 未定义名检查(离线)
_nx_selftest = _load_sub("nx_selftest")
# selftest 引用主脚本近百个符号, 注入主脚本整个命名空间(去 dunder)即可;
# 同时把注入名集传给它, 供 _undefined_name_check 排除。
_nx_selftest.__dict__.update(
    {_k: _v for _k, _v in globals().items() if not _k.startswith("__")})
_nx_selftest.INJECTED_NAMES = set(
    _k for _k in globals() if not _k.startswith("__"))

make_sample_dxf = _nx_selftest.make_sample_dxf
_undefined_name_check = _nx_selftest._undefined_name_check
selftest = _nx_selftest.selftest

def _refresh_display(session, work_part, log=None):
    """末帧强制刷新图形显示: 复刻用户手工"图层全开 + 全部隐藏再显示 + 重建"。

    无界面/批量后新加体·组件·曲线常不自动重绘(旧版尤甚), 数据是对的, 只是视图
    没刷。交互与 batch 两条路径末尾都调它。纯显示、每步 try 兜底, 任一 API 在
    某版本缺失都跳过, 绝不影响模型正确性或中断流程。"""
    if session is None or work_part is None:
        return
    # a) 全部图层置可见(view-based, NX 老版本即有):
    try:
        import NXOpen.Layer as _NL
        _view = work_part.ModelingViews.WorkView
        _states = [_NL.StateInfo(_i, _NL.State.Visible) for _i in range(1, 257)]
        work_part.Layers.SetObjectsVisibilityOnLayer(_view, _states, True)
    except Exception:
        pass
    # b) 逐个体/曲线 Unblank + RedisplayObject(等价"全部隐藏再显示"):
    for _coll in (getattr(work_part, "Bodies", None),
                  getattr(work_part, "Curves", None)):
        if _coll is None:
            continue
        try:
            _objs = list(_coll)
        except Exception:
            _objs = []
        for _o in _objs:
            for _m in ("Unblank", "RedisplayObject"):
                try:
                    getattr(_o, _m)()
                except Exception:
                    pass
    # c) 全量重建:
    for _inv in ("DoRebuilds", "DoUpdateAll"):
        try:
            getattr(session.UpdateManager, _inv)()
            break
        except Exception:
            pass


def batch_run(dxf_arg=None, params_override=None, std_override=None,
              jrt_override=None, new_part_name=None):
    """run_journal 无 UI 直跑(冒烟): 新建部件 → 跑两遍(第二遍验证清理重建)。

    new_part_name 给定时无条件新建该名工作部件(批量测试确定性: 与标准件部件
    等会话内已有部件隔离, 避免 AddComponent 循环装配)。
    """
    import NXOpen
    session = NXOpen.Session.GetSession()
    if new_part_name:
        session.Parts.NewDisplay(new_part_name, NXOpen.Part.Units.Millimeters)
    elif session.Parts.Work is None:
        session.Parts.NewDisplay("cad3d_batch_test",
                                 NXOpen.Part.Units.Millimeters)
    work_part = session.Parts.Work
    state = load_state()
    params = merge_params(state)
    if params_override:
        params.update(params_override)
    std_rules = merge_std_rules(state)
    if std_override:
        std_rules.update(std_override)
        std_rules = {f: r for f, r in std_rules.items() if f in std_override}
    else:
        # 尊重 JSON 选中集(与交互两段式一致); 无记忆=全部非停用件
        saved_sel = (state.get("selected")
                     if state.get("schema") == SCHEMA_VERSION else None)
        if saved_sel is not None and not isinstance(saved_sel, (list, tuple)):
            saved_sel = None       # 坏类型按"无选择记忆"处理
        if saved_sel is not None:
            keep = set(str(f) for f in saved_sel)
            std_rules = {f: r for f, r in std_rules.items() if f in keep}
        else:
            std_rules = {f: r for f, r in std_rules.items()
                         if _rule_usable(r)}
    jrt = merge_jrt(state)
    if jrt_override:
        jrt.update(jrt_override)
    dxf = dxf_arg or resolve_dxf_path(state)
    log = Log(session)
    log("【批量】dxf=%s" % dxf)
    # (P0) 经 notes() 取快照; 循环变量不用 _note——它会遮蔽入队函数 _note(msg)
    for _n in notes():
        log("【配置提示】%s" % _n)
    ok1, stats1 = run_pipeline(dxf, params, session=session, work_part=work_part,
                               log=log, std_rules=std_rules, jrt=jrt)
    ok2, stats2 = run_pipeline(dxf, params, session=session, work_part=work_part,
                                log=log, std_rules=std_rules, jrt=jrt)
    # 末帧刷新: run_pipeline 内部已调 _refresh_display, 这里对 batch 双跑后再兜一次。
    _refresh_display(session, work_part, log)
    feats = 0
    try:
        feats = len([f for f in _iter(work_part.Features)
                     if str(getattr(f, "Name", "")).startswith(FEATURE_PREFIX)])
    except Exception:
        pass
    log("【批量】run1=%s run2=%s 特征数=%d" % (ok1, ok2, feats))
    try:
        with io.open(os.path.join(_logs_dir(), "nx_extrude_report.txt"),
                     "w", encoding="utf-8") as f:
            f.write("\n".join(log.lines))
    except IOError:
        pass
    print("BATCH RESULT run1=%s run2=%s features=%d" % (ok1, ok2, feats))


def main():
    argv = [a for a in sys.argv[1:] if not a.endswith(".py")]
    if "--selftest" in argv:
        i = argv.index("--selftest")
        arg = argv[i + 1] if i + 1 < len(argv) and not argv[i + 1].startswith("--") else None
        sys.exit(0 if selftest(arg) else 1)
    if "--make-sample-dxf" in argv:
        i = argv.index("--make-sample-dxf")
        out = argv[i + 1] if i + 1 < len(argv) else os.path.join(
            script_dir(), "sample_layers.dxf")
        make_sample_dxf(out)
        print("sample dxf -> %s" % out)
        return

    # 以下需要 NX 环境
    try:
        import NXOpen  # noqa: F401
    except ImportError:
        print("本脚本需要在 NX 中运行(工具→日记→播放), "
              "或用 --selftest / --make-sample-dxf 做无 NX 自测。")
        return

    if "--batch" in argv:
        i = argv.index("--batch")
        arg = argv[i + 1] if i + 1 < len(argv) and not argv[i + 1].startswith("--") else None
        batch_run(arg)
        return

    # 常规: 三段式 —— ①标准件选择(有件才弹; 取消=中止) ②主参数(OK只收集) ③标准件参数(执行)
    theSession = NXOpen.Session.GetSession()
    if theSession.Parts.Work is None:
        NXOpen.UI.GetUI().NXMessageBox.Show(
            "CAD3D", NXOpen.NXMessageBox.DialogType.Warning,
            "请先新建或打开一个部件(需要工作部件)。")
        return

    _startup_notes = notes()       # (P0) 经访问器取快照, 不直接依赖全局列表
    if _startup_notes:             # 配置/记忆加载异常: 醒目提示, 不静默回退
        NXOpen.UI.GetUI().NXMessageBox.Show(
            "CAD3D 配置提示", NXOpen.NXMessageBox.DialogType.Warning,
            "\n".join(_startup_notes))

    state = load_state()
    params = merge_params(state)
    std_rules_all = merge_std_rules(state)
    jrt = merge_jrt(state)

    # 第一段: 标准件选择(记忆上次选择; 新件默认不勾; 无件跳过)
    selected = None
    if std_rules_all:
        saved_sel = (state.get("selected")
                     if state.get("schema") == SCHEMA_VERSION else None)
        if saved_sel is None:      # 旧 JSON: 全不勾(用户自选; 防串值)
            saved_sel = []
        elif not isinstance(saved_sel, (list, tuple)):
            saved_sel = []         # 坏类型(数字/dict 等)按无勾选处理
        else:                      # 清掉已删除的件; 新件(不在记忆里)默认不勾
            saved_sel = [f for f in saved_sel
                         if f in std_rules_all
                         and _rule_usable(std_rules_all[f])]
        sel_dlx_path = _fresh_dlx_path("nx_std_select")
        try:
            with io.open(sel_dlx_path, "w", encoding="utf-8", newline="\n") as f:
                f.write(build_selection_dlx(sorted(std_rules_all), saved_sel))
        except IOError:
            sel_dlx_path = None
        if not (sel_dlx_path and os.path.isfile(sel_dlx_path)):
            # 选件窗口不可用: 取上次勾选∩现有件(空则全部可用件), 不崩不中断
            selected = [f for f in sorted(std_rules_all)
                        if f in set(saved_sel)
                        and _rule_usable(std_rules_all[f])]
            if not selected:
                selected = [f for f in sorted(std_rules_all)
                            if _rule_usable(std_rules_all[f])]
        else:
            seldlg = None
            try:
                seldlg = SelectionDialog(sel_dlx_path,
                                         sorted(std_rules_all), saved_sel)
                selected = seldlg.Launch()
            except Exception as ex:
                NXOpen.UI.GetUI().NXMessageBox.Show(
                    "CAD3D", NXOpen.NXMessageBox.DialogType.Error,
                    "选择对话框启动失败: %s" % ex)
                return
            finally:
                if seldlg is not None:
                    seldlg.Dispose()
            if selected is None:   # 取消 → 中止整个流程
                return
            # 选择即刻落盘(此后窗口②/③取消都不丢勾选记忆)
            save_state(state.get("dxf_path") or resolve_dxf_path(state),
                       params, std_rules_all, selected=selected,
                       jrt_se=(state.get("jrt_se")
                               if state.get("schema") == SCHEMA_VERSION
                               else None),
                       jt_link_mode=(state.get("jt_link_mode")
                                     if state.get("schema") == SCHEMA_VERSION
                                     else None))
        std_rules = {f: std_rules_all[f] for f in selected}
    else:
        std_rules = {}

    # 第二段: 主参数窗口(FLB/图层/JRT; 无标准件组; OK 只收集不执行)
    dlx = write_dlx(params, jrt, jt_mode_with_memory(state))
    if not dlx:
        NXOpen.UI.GetUI().NXMessageBox.Show(
            "CAD3D", NXOpen.NXMessageBox.DialogType.Error, ".dlx 对话框文件生成失败。")
        return

    dlg = None
    try:
        dlg = ParamDialog(dlx, std_rules=None, selected=selected,
                          execute_on_ok=False)
        dlg.Launch()
    except Exception as ex:
        # 回退链: 脚本目录失败 → TEMP 重试(对应 dt:find-dcl)
        try:
            import tempfile
            dlx2 = _fresh_dlx_path("nx_extrude_runner",
                                   base_dir=tempfile.gettempdir())
            with io.open(dlx2, "w", encoding="utf-8", newline="\n") as f:
                f.write(build_dlx(params, jrt,
                        jt_mode_with_memory(state)))
            dlg = ParamDialog(dlx2, std_rules=None, selected=selected,
                              execute_on_ok=False)
            dlg.Launch()
        except Exception as ex2:
            NXOpen.UI.GetUI().NXMessageBox.Show(
                "CAD3D", NXOpen.NXMessageBox.DialogType.Error,
                "对话框启动失败:\n%s\n\n(回退也失败: %s)" % (ex, ex2))
            return
    finally:
        if dlg is not None:
            dlg.Dispose()
    if dlg is None or dlg.result_params is None:
        return                          # 窗口②取消 → 中止
    params2 = dlg.result_params
    jrt2 = dlg.result_jrt
    dxf2 = dlg.result_dxf
    mode2 = dlg.result_mode or jt_mode_with_memory(state)

    # 第二页参数即刻落盘(窗口③取消也不丢; 规则仍由窗口③/执行链路保存)
    try:
        save_state(dxf2 or resolve_dxf_path(state), params2, std_rules_all,
                   selected=selected,
                   jrt_se=[float(jrt2.get("start", 0.0)),
                           float(jrt2.get("end", 0.0))],
                   jt_link_mode=mode2)
    except (TypeError, ValueError):
        pass

    # 第三段: 标准件参数窗口(每件一个可收起组; OK/Apply 执行; 取消=中止)
    if std_rules:
        sdx = write_std_dlx(std_rules, params2)
        if not sdx:
            NXOpen.UI.GetUI().NXMessageBox.Show(
                "CAD3D", NXOpen.NXMessageBox.DialogType.Error,
                "标准件参数 .dlx 生成失败。")
            return
        sdlg = None
        try:
            sdlg = StdParamsDialog(sdx, std_rules, params2, jrt2, dxf2,
                                   selected, std_rules_all=std_rules_all,
                                   jt_mode=mode2)
            sdlg.Launch()
        except Exception as ex:
            NXOpen.UI.GetUI().NXMessageBox.Show(
                "CAD3D", NXOpen.NXMessageBox.DialogType.Error,
                "标准件参数对话框启动失败: %s" % ex)
        finally:
            if sdlg is not None:
                sdlg.Dispose()
    else:
        # 无选中标准件: 直接执行
        execute_pipeline(dxf2, params2, jrt2, {}, theSession,
                         std_rules_all=std_rules_all, selected=selected or [],
                     jt_link_mode=mode2)


if __name__ == "__main__":
    main()


# ============================================================================
# 附: .dlx 块模板来源(本机 NX2312 官方文件, 供维护比对)
#   group/Members 结构  : UGOPEN\SampleNXOpenApplications\Python\BlockStyler\ChangeFaceColor\ChangeFaceColor.dlx
#   UICOMP_double       : DESIGN_TOOLS\checkmate\examples\NXOpenCheckerExamples\Python\CheckDeepHoles\...dlx
#   UICOMP_label        : 同上
#   NativeFileBrowser   : DRAFTING\aec_documentation\splmshare\AEC_Documentation\Application\Excel2Spline.dlx
#   double 块 Python 取值(.Value) : ...\BlockStyler\MatrixOperations\MatrixOperations.py
#   回调类模式          : ...\BlockStyler\ChangeFaceColor\ChangeFaceColor.py
# ============================================================================
