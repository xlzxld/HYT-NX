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

# ============================================================================
# §5 NX 建模流水线 —— 建模内核/标准件已拆至 nx_nxcore.py 与 nx_stdparts.py;
# 特征登记表(FeatureRegistry/registry)留在主脚本, 经注入让各子模块共享
# 同一实例(谁持有 registry 谁负责, 清理/移除参数语义不变)。
# ============================================================================

# nx_nxcore: NX 建模内核(清理/建曲线/拉伸/分层建模/移除参数)
_nx_nxcore = _inject(_load_sub("nx_nxcore"),
                     SCRIPT_VERSION=SCRIPT_VERSION,
                     FEATURE_PREFIX=FEATURE_PREFIX,
                     COMP_PREFIX=COMP_PREFIX,
                     CHAIN_TOL=CHAIN_TOL,
                     MANAGED_MIN=MANAGED_MIN,
                     MANAGED_MAX=MANAGED_MAX,
                     LAYER_TABLE=LAYER_TABLE,
                     REF_LAYER_TABLE=REF_LAYER_TABLE,
                     TARGET_CODE=TARGET_CODE,
                     registry=registry,
                     organize_loops=organize_loops,
                     _nx_curve_fp=_nx_curve_fp,
                     dxf_fingerprints=dxf_fingerprints)

# 再导出(run_pipeline/test/batch_smoke 按原名可见):
MARK_ATTR = _nx_nxcore.MARK_ATTR
_mark_curve = _nx_nxcore._mark_curve
_is_marked = _nx_nxcore._is_marked
_iter = _nx_nxcore._iter
_bodies_of = _nx_nxcore._bodies_of
_fmt_num = _nx_nxcore._fmt_num
Log = _nx_nxcore.Log
nx_purge = _nx_nxcore.nx_purge
ensure_categories = _nx_nxcore.ensure_categories
create_curves = _nx_nxcore.create_curves
work_part_rules = _nx_nxcore.work_part_rules
_add_to_section_compat = _nx_nxcore._add_to_section_compat
_sc_rule_options = _nx_nxcore._sc_rule_options
_set_expr = _nx_nxcore._set_expr
extrude_curves = _nx_nxcore.extrude_curves
modeling_ents = _nx_nxcore.modeling_ents
build_layer = _nx_nxcore.build_layer
_remove_parameters = _nx_nxcore._remove_parameters

# nx_stdparts: 标准件放置(锚点/AddComponent/提升体/布尔)
_nx_stdparts = _inject(_load_sub("nx_stdparts"),
                       registry=registry,
                       FEATURE_PREFIX=FEATURE_PREFIX,
                       COMP_PREFIX=COMP_PREFIX,
                       STD_MAX_ANCHORS=STD_MAX_ANCHORS,
                       _iter=_iter,
                       _bodies_of=_bodies_of,
                       _rule_usable=_rule_usable,
                       _unusable_names=_unusable_names,
                       stdparts_dir=stdparts_dir,
                       anchors_overflow=anchors_overflow,
                       collect_circle_anchors=collect_circle_anchors,
                       _std_z=_std_z,
                       _place_delta=_place_delta)

# 再导出(run_pipeline/tools/nx_zero_ref/test 按原名可见):
_matrix3x3 = _nx_stdparts._matrix3x3
_pick_target = _nx_stdparts._pick_target
_promote_body = _nx_stdparts._promote_body
_bool_one = _nx_stdparts._bool_one
_bool_feature = _nx_stdparts._bool_feature
_usable_parts = _nx_stdparts._usable_parts
place_std_parts = _nx_stdparts.place_std_parts

# ---------------------------------------------------------------------------
# (P5→P7) JRT 子模块加载与注入 —— 依赖 nx_nxcore/nx_stdparts 的再导出,
# 故必须放在两者之后。
# ---------------------------------------------------------------------------
# nx_jrt_geom: 加热条几何判据(纯逻辑, 无注入依赖)
_nx_jrt_geom = _load_sub("nx_jrt_geom")

# 再导出(selftest 直接引用这些判据; nx_jrt 经注入取用):
_jrt_sides = _nx_jrt_geom._jrt_sides
_faces_healthy = _nx_jrt_geom._faces_healthy
_body_face_rows = _nx_jrt_geom._body_face_rows
_flush_start_r = _nx_jrt_geom._flush_start_r
_dome_body_ok = _nx_jrt_geom._dome_body_ok
_blend_ok = _nx_jrt_geom._blend_ok
_chain_tips = _nx_jrt_geom._chain_tips
_cluster_tips = _nx_jrt_geom._cluster_tips
_chain_outlet_mids = _nx_jrt_geom._chain_outlet_mids
_chain_connectors = _nx_jrt_geom._chain_connectors
_conn_face_pick = _nx_jrt_geom._conn_face_pick
_merge_open_chains = _nx_jrt_geom._merge_open_chains

# nx_jrt: 加热条 NX 工序(NXOpen 函数内延迟 import, 离线可加载)
_nx_jrt = _inject(_load_sub("nx_jrt"),
                  find_chains=find_chains,
                  _sc_rule_options=_sc_rule_options,
                  _fmt_num=_fmt_num,
                  registry=registry,
                  _mark_curve=_mark_curve,
                  extrude_curves=extrude_curves,
                  _bool_feature=_bool_feature,
                  _pick_target=_pick_target,
                  _bodies_of=_bodies_of,
                  DEFAULT_JRT=DEFAULT_JRT,
                  TARGET_CODE=TARGET_CODE,
                  LAYER_CODES=LAYER_CODES,
                  FEATURE_PREFIX=FEATURE_PREFIX,
                  _faces_healthy=_faces_healthy,
                  _body_face_rows=_body_face_rows,
                  _dome_body_ok=_dome_body_ok,
                  _blend_ok=_blend_ok,
                  _chain_outlet_mids=_chain_outlet_mids,
                  _chain_connectors=_chain_connectors,
                  _conn_face_pick=_conn_face_pick,
                  _merge_open_chains=_merge_open_chains,
                  _jrt_sides=_jrt_sides)

# 再导出(run_pipeline 调 build_jrt; 其余工序函数按原名可见):
_uf_face_data = _nx_jrt._uf_face_data
_find_flat_face = _nx_jrt._find_flat_face
_edge_blend_end = _nx_jrt._edge_blend_end
_body_volume = _nx_jrt._body_volume
_edge_blend_end_retry = _nx_jrt._edge_blend_end_retry
_delete_faces = _nx_jrt._delete_faces
_delete_faces_safe = _nx_jrt._delete_faces_safe
_pick_conn_faces = _nx_jrt._pick_conn_faces
_set_display = _nx_jrt._set_display
build_jrt = _nx_jrt.build_jrt

# §5.6 JRT 加热条(nx_jrt_geom.py 纯判据 + nx_jrt.py NX 工序)已拆出,
# 由上方注入并再导出(同名可见, run_pipeline/selftest 调用方零改动)。

# §5.6 JRT 加热条(nx_jrt_geom.py 纯判据 + nx_jrt.py NX 工序)已拆出,
# 由加载器注入并再导出(同名可见, run_pipeline/selftest 调用方零改动)。

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
# §6 对话框 —— 已搬至 nx_dialogs.py, 此处加载并注入(依赖在本块之前已全部就绪:
# run_pipeline/Log 定义于 §5, 常量在 §0, nx_rules/nx_dlx 在加载器区已再导出)
# ============================================================================
_nx_dialogs = _inject(_load_sub("nx_dialogs"),
                      run_pipeline=run_pipeline,
                      Log=Log,
                      _note=_note,
                      DIALOG_GROUPS=DIALOG_GROUPS,
                      LAYER_TABLE=LAYER_TABLE,
                      JRT_FIELDS=JRT_FIELDS,
                      DEFAULT_JRT=DEFAULT_JRT,
                      JT_LINK_OPTS=JT_LINK_OPTS,
                      JT_LINK_MODES=JT_LINK_MODES,
                      LAYER_CODES=LAYER_CODES,
                      DEFAULT_STD_RULE=DEFAULT_STD_RULE,
                      LAYER_SEL_OPTS=LAYER_SEL_OPTS,
                      ZMODE_OPTS=ZMODE_OPTS,
                      BOOL_OPTS=BOOL_OPTS,
                      DIR_OPTS=DIR_OPTS,
                      load_state=load_state,
                      merge_params=merge_params,
                      merge_std_rules=merge_std_rules,
                      jrt_with_memory=jrt_with_memory,
                      jt_mode_with_memory=jt_mode_with_memory,
                      resolve_dxf_path=resolve_dxf_path,
                      save_state=save_state,
                      sanitize_std_rule=sanitize_std_rule,
                      std_part_defaults=std_part_defaults,
                      _std_z=_std_z,
                      derive_linked=derive_linked,
                      _jt_link_values=_jt_link_values,
                      _cx_link_values=_cx_link_values,
                      _logs_dir=_logs_dir,
                      _opt_index=_opt_index)

# 再导出(main 三段式流程与 selftest(_BlockDialogBase) 按原名可见):
_dlg_show = _nx_dialogs._dlg_show
SelectionDialog = _nx_dialogs.SelectionDialog
execute_pipeline = _nx_dialogs.execute_pipeline
_BlockDialogBase = _nx_dialogs._BlockDialogBase
ParamDialog = _nx_dialogs.ParamDialog
StdParamsDialog = _nx_dialogs.StdParamsDialog

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
