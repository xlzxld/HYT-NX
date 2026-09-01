# -*- coding: utf-8 -*-
"""
nx_extrude_runner.py — NX 2312 分层拉伸自动化（CAD DXF → 3D）  v1.36  2026-09-02

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

SCRIPT_VERSION = "1.36"


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
    ("grp_plain", "普通拉伸图层（起始=结束=0 则跳过）", ["JT", "CX"]),
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


def derive_linked(top, bottom):
    """FLB top/bottom → 联动层参数 {code: (v1, v2)} + JRT 区间。"""
    out = {code: fn(top, bottom) for code, fn in LINK_RULES.items()}
    out["JRT"] = (top, top - JRT_FROM_TOP)
    return out

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
ZMODE_OPTS     = [(k, lbl + "+偏移") for k, lbl, _ly, _sd in _ZMODE_DEFS]
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

def jrt_with_memory(state, params):
    """打开时的加热条参数: 三几何参数恒默认; 起始/结束有记忆用记忆,
    无记忆按 FLB 当前参数联动。"""
    jrt = dict(DEFAULT_JRT)
    se = None
    if state.get("schema") == SCHEMA_VERSION:
        v = state.get("jrt_se")
        if isinstance(v, (list, tuple)) and len(v) == 2:
            try:
                se = (float(v[0]), float(v[1]))
            except (TypeError, ValueError):
                se = None
    if se is None:
        s, e = params.get(TARGET_CODE, (0.0, 0.0))
        se = derive_linked(max(s, e), min(s, e)).get(
            "JRT", (DEFAULT_JRT["start"], DEFAULT_JRT["end"]))
    jrt["start"], jrt["end"] = se
    return jrt


# 单件最大放置数量护栏(nx_std_config.STD_MAX_ANCHORS 可调; 非法回默认)
STD_MAX_ANCHORS = (_cfg_int("STD_MAX_ANCHORS", 200))


def anchors_overflow(anchors, rule):
    """(纯逻辑) 数量超限或"空图层+大半径"指纹 → True。"""
    if len(anchors) > STD_MAX_ANCHORS:
        return True
    return (not rule.get("layer")) and float(rule.get("r_max", 0.0)) >= 999.0


def stdparts_dir():
    return os.path.join(script_dir(), STDPARTS_DIRNAME)


def std_part_defaults(fname, table=None):
    """件的默认规则(两级匹配)或 None(无默认——新件)。

    v1.30 两级匹配: 精确文件名行(带/不带 .prt)优先于关键词子串行;
    每件实测的参考点写在精确行里。table 参数供 selftest 注入测试表。
      主进胶(DP,0~8,FLB底,仅放置) 垫片(DK,0~5,FLB顶,放置+减去)
      大水口/点胶口(RZ,0~15,FLB底,仅放置) 螺丝(LS,0~5,FLB顶,放置+减去)
    恢复默认按钮仅对返回非 None 的件显示(无默认的新件点按钮=无效不报错)。
    """
    # 出厂默认表在 nx_std_config.py(注释齐全可自行编辑); 这里只是
    # 配置文件缺失时的内置兜底(内容同款)。
    if table is None and _USER_CFG is not None:
        try:
            table = [(str(k), dict(v))
                     for k, v in _USER_CFG.STD_PART_DEFAULTS]
        except Exception:
            table = None
    if not table:
        table = (
            ("主进胶", {"layer": "DP", "r_min": 0.0, "r_max": 8.0,
                      "z_mode": "FLB_BOTTOM",
                      "bool_mode": "PLACE_SUBTRACT"}),
            ("大水口", {"layer": "RZ", "r_min": 0.0, "r_max": 15.0,
                      "z_mode": "FLB_BOTTOM"}),
            ("点胶口", {"layer": "RZ", "r_min": 0.0, "r_max": 15.0,
                      "z_mode": "FLB_BOTTOM"}),
            ("热咀", {"layer": "RZ", "r_min": 0.0, "r_max": 15.0,
                     "z_mode": "FLB_BOTTOM"}),
            ("nozzle", {"layer": "RZ", "r_min": 0.0, "r_max": 15.0,
                       "z_mode": "FLB_BOTTOM"}),
            ("螺丝", {"layer": "LS", "r_min": 0.0, "r_max": 5.0,
                    "z_mode": "FLB_TOP", "bool_mode": "PLACE_SUBTRACT"}),
            ("screw", {"layer": "LS", "r_min": 0.0, "r_max": 5.0,
                     "z_mode": "FLB_TOP", "bool_mode": "PLACE_SUBTRACT"}),
            ("ls-", {"layer": "LS", "r_min": 0.0, "r_max": 5.0,
                   "z_mode": "FLB_TOP", "bool_mode": "PLACE_SUBTRACT"}),
            ("接线盒", {"layer": "CXK", "z_mode": "CX_TOP"}),
            ("垫片", {"layer": "DK", "r_min": 0.0, "r_max": 5.0,
                    "z_mode": "FLB_TOP", "bool_mode": "PLACE_SUBTRACT"}),
            ("washer", {"layer": "DK", "r_min": 0.0, "r_max": 5.0,
                      "z_mode": "FLB_TOP", "bool_mode": "PLACE_SUBTRACT"}),
        )
    low = fname.lower()
    stem = low[:-4] if low.endswith('.prt') else low
    for key, over in table:
        k = key.lower()
        if k == low or k == stem or k == stem + '.prt':
            r = dict(DEFAULT_STD_RULE)
            r.update(over)
            return r
    for key, over in table:
        if key.lower() in low:
            r = dict(DEFAULT_STD_RULE)
            r.update(over)
            return r
    return None


def guess_std_rule(fname):
    """按文件名猜默认规则(无命中回通用默认; ref 必填由 config 提供)。"""
    d = std_part_defaults(fname)
    return d if d is not None else dict(DEFAULT_STD_RULE)


def sanitize_std_rule(rule):
    """规则字段规范化(坏值回默认, r_min/r_max 保序)。"""
    out = dict(DEFAULT_STD_RULE)
    if not isinstance(rule, dict):
        return out
    lay = str(rule.get("layer", "") or "").upper()
    out["layer"] = lay if lay in LAYER_CODES + ["CXK"] else ""
    for k in ("r_min", "r_max", "off_x", "off_y", "off_z"):
        try:
            out[k] = float(rule.get(k, out[k]))
        except (TypeError, ValueError):
            pass
    if out["r_max"] < out["r_min"]:
        out["r_min"], out["r_max"] = out["r_max"], out["r_min"]
    if rule.get("z_mode") in [k for k, _l, _ly, _sd in _ZMODE_DEFS]:
        out["z_mode"] = rule["z_mode"]
    if rule.get("bool_mode") in [v for v, _t in BOOL_OPTS]:
        out["bool_mode"] = rule["bool_mode"]
    if rule.get("dir") in [v for v, _t in DIR_OPTS]:
        out["dir"] = rule["dir"]
    ref = rule.get("ref")
    if isinstance(ref, (list, tuple)) and len(ref) == 3:
        try:
            out["ref"] = [float(ref[0]), float(ref[1]), float(ref[2])]
        except (TypeError, ValueError):
            out["ref"] = None
    else:
        out["ref"] = None
    return out


def _rule_usable(rule):
    """(纯逻辑) 规则可用 = ref 为 3 个数字。"""
    ref = rule.get("ref") if isinstance(rule, dict) else None
    return (isinstance(ref, (list, tuple)) and len(ref) == 3
            and all(isinstance(v, float) for v in ref))

def _unusable_names(rules):
    """(纯逻辑) {文件名: 规则} → 未配置 ref 的文件名排序列表。"""
    return sorted(f for f, r in rules.items() if not _rule_usable(r))

def discover_std_parts():
    """扫描 stdparts 目录下 .prt(目录不存在则创建) → 排序文件名列表。"""
    d = stdparts_dir()
    try:
        os.makedirs(d, exist_ok=True)
    except OSError:
        return []
    try:
        return sorted(n for n in os.listdir(d) if n.lower().endswith(".prt"))
    except OSError:
        return []


def merge_std_rules(state):
    """发现到的文件 × (JSON 记忆 | 文件名猜测) → {文件名: 规范化规则}。

    v1.9: JSON 带 schema:2 才读记忆(旧 JSON 的规则字段已改, 忽略防
    旧记忆覆盖新默认); 首次保存后恢复正常记忆。
    """
    if state.get("schema") != SCHEMA_VERSION:
        state = {}
    saved = state.get("std_parts") or {}
    out = {}
    for fname in discover_std_parts():
        out[fname] = sanitize_std_rule(saved.get(fname) or guess_std_rule(fname))
    return out


def merge_jrt(state):
    """JRT 参数: 每次固定默认(3.9/0.1/3.7), 不再读 JSON 记忆。

    (v1.9 教训: JSON 记忆覆盖默认值, 用户改过一次后默认值就"变了";
    start/end 由对话框 FLB 联动实时刷新, 也无需记忆。)
    """
    return dict(DEFAULT_JRT)


def script_dir():
    """脚本所在目录(journal 播放时 sys.argv[0] 即本文件路径)。"""
    try:
        return os.path.dirname(os.path.abspath(__file__))
    except NameError:
        return os.path.dirname(os.path.abspath(sys.argv[0]))


def default_params():
    return {r[0]: (float(r[3]), float(r[4])) for r in LAYER_TABLE}


# ============================================================================
# §1 DXF 解析器(纯 Python, 无 NX 依赖)
# ============================================================================

class DXLine(object):
    __slots__ = ("p1", "p2")
    kind = "line"
    def __init__(self, p1, p2):
        self.p1, self.p2 = p1, p2


class DXArc(object):
    __slots__ = ("c", "r", "a0", "a1")     # 角度: 弧度, CCW a0→a1
    kind = "arc"
    def __init__(self, c, r, a0, a1):
        self.c, self.r, self.a0, self.a1 = c, r, a0, a1
    @property
    def p1(self):
        return (self.c[0] + self.r * math.cos(self.a0),
                self.c[1] + self.r * math.sin(self.a0))
    @property
    def p2(self):
        return (self.c[0] + self.r * math.cos(self.a1),
                self.c[1] + self.r * math.sin(self.a1))


class DXCircle(object):
    __slots__ = ("c", "r")
    kind = "circle"
    def __init__(self, c, r):
        self.c, self.r = c, r


def _read_dxf_text(path):
    """DXF 文本读取: 优先 UTF-8, 失败按 GBK($DWGCODEPAGE=ANSI_936), 再失败 replace。"""
    with open(path, "rb") as _f:
        raw = _f.read()
    for enc in ("utf-8-sig", "utf-8", "gbk"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("gbk", errors="replace")


def parse_dxf(path):
    """解析 DXF 的 ENTITIES 段(建模只认 LINE/CIRCLE/ARC, 与 offset_runner
    生成物一致)。

    返回 (layers, stats):
      layers: {图层名大写: [DXLine/DXArc/DXCircle, ...]}
      stats : {"ref_layers": {非建模图层名: 数},
               "unsupported": {实体类型: 数},       # 全部不支持的(含参考图层)
               "unsupported_model": 数,             # 其中的建模图层部分(弹窗口径)
               "nonplanar": 数, "total": 数}        # total 只计受支持实体
    """
    lines = _read_dxf_text(path).splitlines()
    n = len(lines)
    pairs = []
    for i in range(0, n - 1, 2):
        pairs.append((lines[i].strip(), lines[i + 1].strip("\r\n")))

    layers, stats = {}, {"ref_layers": {}, "unsupported": {},
                         "unsupported_model": 0, "nonplanar": 0, "total": 0}

    # 定位 ENTITIES 段(记起点, 实体切到 ENDSEC 为止)
    start = None
    for i in range(1, len(pairs)):
        if pairs[i] == ("2", "ENTITIES") and pairs[i - 1] == ("0", "SECTION"):
            start = i
            break
    if start is None:
        return layers, stats

    def entities_of(seg_pairs):
        """把 (code,val) 序列切成实体块 [{code: first-val}] 列表。

        全部实体类型都切块输出(含不支持的)——支持与否由上层判定并统计,
        保证 LWPOLYLINE 等被丢弃时有计数与警告, 不静默丢几何(v1.35)。
        """
        out, cur, ctype = [], None, None
        for code, val in seg_pairs:
            if code == "0":
                if ctype is not None:
                    out.append(cur)
                ctype = val
                cur = {"0": val}
            elif ctype is not None and code not in cur:
                cur[code] = val
        if ctype is not None:
            out.append(cur)
        return out

    seg2 = []
    for k in range(start, len(pairs)):   # 从 ENTITIES 段起, 截到 ENDSEC
        code, val = pairs[k]
        if code == "0" and val == "ENDSEC":
            break
        seg2.append((code, val))

    for e in entities_of(seg2):
        etype = e.get("0") or "?"
        if etype not in ("LINE", "CIRCLE", "ARC"):
            # LWPOLYLINE/SPLINE/INSERT 等: 计数并警告, 不静默丢(v1.35)
            layer = (e.get("8") or "0").upper()
            stats["unsupported"][etype] = \
                stats["unsupported"].get(etype, 0) + 1
            if layer in LAYER_CODES:
                stats["unsupported_model"] += 1
            continue
        stats["total"] += 1
        layer = (e.get("8") or "0").upper()
        if layer not in LAYER_CODES:
            stats["ref_layers"][layer] = stats["ref_layers"].get(layer, 0) + 1
            # 参考图层照常保留(导入 NX 但不建模)

        def fnum(key):
            return float(e.get(key, "0") or "0")

        z = fnum("30")
        if abs(z) > 1e-9:
            stats["nonplanar"] += 1
        try:
            if etype == "LINE":
                obj = DXLine((fnum("10"), fnum("20")), (fnum("11"), fnum("21")))
                if math.hypot(obj.p2[0] - obj.p1[0], obj.p2[1] - obj.p1[1]) < 1e-9:
                    continue                      # 零长线丢弃
            elif etype == "CIRCLE":
                obj = DXCircle((fnum("10"), fnum("20")), fnum("40"))
            else:                                  # ARC
                a0, a1 = math.radians(float(e["50"])), math.radians(float(e["51"]))
                if a1 <= a0:
                    a1 += 2.0 * math.pi
                obj = DXArc((fnum("10"), fnum("20")), fnum("40"), a0, a1)
        except (KeyError, ValueError) as ex:
            k = "<解析失败:%s>" % ex
            stats["unsupported"][k] = stats["unsupported"].get(k, 0) + 1
            continue
        layers.setdefault(layer, []).append(obj)
    return layers, stats


# ============================================================================
# §2 环链几何(纯 Python 可自测): 端点连链 → 封闭环/开口链 → 嵌套分组
# ============================================================================

def _pkey(p, tol=LOOP_TOL):
    return (int(round(p[0] / tol)), int(round(p[1] / tol)))


def _near_keys(p, tol=LOOP_TOL):
    """端点所在量化桶及 3×3 邻桶。

    (v1.35) 此前只查单桶: 两点间距 <tol 但跨量化格边界时永远配不上,
    该闭合的链被判开 → 轮廓不拉伸/JRT 多画桥接线。
    """
    kx, ky = _pkey(p, tol)
    return [(kx + dx, ky + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)]


def find_chains(segs):
    """把线/弧按端点重合连成链(容差 LOOP_TOL, 3×3 邻桶搜索)。

    返回 (closed, open_): closed=[[(idx, rev), ...] 每项为(曲线索引, 是否反向)],
    闭合链首尾相接; open_ 为两端悬空的链。
    (v1.35) 端点三叉及以上(T 形相接/重复线)时, 不再按字典序任意配对,
    优先取"方向延续性最好"的段——纯任意配对会把两条共端点轮廓串成错链。
    """
    from collections import defaultdict
    ep = defaultdict(list)
    for i, s in enumerate(segs):
        if s.kind == "circle":
            continue
        ep[_pkey(s.p1)].append((i, 0))
        ep[_pkey(s.p2)].append((i, 1))

    used = [False] * len(segs)

    def _take(pt, prev_pt):
        """邻桶内找未用段: 与链方向延续性最好、其次距离最近的端点配对。"""
        vx = pt[0] - prev_pt[0]
        vy = pt[1] - prev_pt[1]
        vlen = math.hypot(vx, vy)
        best = None
        for k in _near_keys(pt):
            for (j, e) in ep.get(k, ()):
                if used[j]:
                    continue
                q = segs[j].p1 if e == 0 else segs[j].p2
                d = math.hypot(q[0] - pt[0], q[1] - pt[1])
                if d > LOOP_TOL:
                    continue
                other = segs[j].p2 if e == 0 else segs[j].p1
                ux, uy = other[0] - q[0], other[1] - q[1]
                ulen = math.hypot(ux, uy)
                # turn=1−cosθ: 直线延续→0, 折返→2; 无方向(链首)时 0.5 中性
                if vlen > 1e-12 and ulen > 1e-12:
                    turn = 1.0 - (ux * vx + uy * vy) / (ulen * vlen)
                else:
                    turn = 0.5
                cand = (turn, d, j, e)
                if best is None or cand[:2] < best[:2]:
                    best = cand
        if best is None:
            return None
        _turn, _d, j, e = best
        used[j] = True
        return j, e

    closed, open_ = [], []
    for i in range(len(segs)):
        if used[i] or segs[i].kind == "circle":
            continue
        used[i] = True
        chain = [(i, False)]
        # 从链头(i 的 p1)与链尾(i 的 p2)双向延伸
        for direction in ("tail", "head"):
            pt = segs[i].p1 if direction == "tail" else segs[i].p2
            prev_pt = segs[i].p2 if direction == "tail" else segs[i].p1
            forward = direction == "head"
            while True:
                got = _take(pt, prev_pt)
                if got is None:
                    break
                j, e = got
                # e: 曲线 j 与当前链端相连的端(0=p1, 1=p2); 判定进入方向
                rev = (e == 1)
                if forward:
                    chain.append((j, rev))
                else:
                    chain.insert(0, (j, not rev))
                prev_pt = pt
                pt = segs[j].p1 if e == 1 else segs[j].p2
        head_pt = segs[chain[0][0]].p1 if not chain[0][1] else segs[chain[0][0]].p2
        tail_pt = segs[chain[-1][0]].p2 if not chain[-1][1] else segs[chain[-1][0]].p1
        if _pkey(head_pt) == _pkey(tail_pt):
            closed.append(chain)
        else:
            open_.append(chain)
    return closed, open_


def loop_polygon(chain, segs, arc_step_deg=10.0):
    """把链离散为多边形顶点序列(用于包含测试/面积), 按链遍历方向。"""
    pts = []
    for idx, rev in chain:
        s = segs[idx]
        if s.kind == "line":
            a, b = (s.p2, s.p1) if rev else (s.p1, s.p2)
            if not pts:
                pts.append(a)
            pts.append(b)
        else:  # arc
            a0, a1 = s.a0, s.a1
            if rev:
                a0, a1 = a1, a0
            if not pts:
                pts.append((s.c[0] + s.r * math.cos(a0), s.c[1] + s.r * math.sin(a0)))
            span = a1 - a0
            steps = max(2, int(math.ceil(abs(span) / math.radians(arc_step_deg))))
            for k in range(1, steps + 1):
                ang = a0 + span * k / steps
                pts.append((s.c[0] + s.r * math.cos(ang), s.c[1] + s.r * math.sin(ang)))
    return pts


def poly_area(poly):
    s = 0.0
    for i in range(len(poly)):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % len(poly)]
        s += x1 * y2 - x2 * y1
    return s / 2.0


def _bbox(poly):
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    return (min(xs), min(ys), max(xs), max(ys))


def point_in_poly(pt, poly):
    x, y = pt
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > y) != (yj > y):
            xx = xi + (y - yi) * (xj - xi) / (yj - yi)
            if x < xx:
                inside = not inside
        j = i
    return inside


def _loop_in_loop(poly_a, poly_b, samples=8):
    """环 A 是否被环 B 包含: 取 A 的至多 samples 个顶点投票(射线法)。

    (v1.35) 此前只用 A 的首顶点——首顶点恰落在 B 的边上(相切/共边)时
    判定随机; 多点投票对"真包含"(多数点在内)与"部分重叠"(少数点在内)
    区分更稳。
    """
    n = len(poly_a)
    step = max(1, n // samples)
    pts = poly_a[::step][:samples]
    hits = sum(1 for p in pts if point_in_poly(p, poly_b))
    return hits * 2 > len(pts)


def organize_loops(segs):
    """图层曲线 → 轮廓组织。

    返回 (profiles, opens, n_circles):
      profiles = [{"outer": poly, "outer_chain": chain, "holes": [(chain, poly), ...]}, ...]
      opens    = 开口链列表(警告用)
      圆独立成 profile(无 holes)。
    """
    closed, opens = find_chains(segs)
    loops = []
    for chain in closed:
        poly = loop_polygon(chain, segs)
        if len(poly) < 3:
            continue
        loops.append({"chain": chain, "poly": poly, "area": abs(poly_area(poly)),
                      "bbox": _bbox(poly)})
    for s in segs:
        if s.kind == "circle":
            cx, cy = s.c
            r = s.r
            # 圆用 8 边形近似即可满足包含/面积判定
            poly = [(cx + r * math.cos(math.pi / 4 * k), cy + r * math.sin(math.pi / 4 * k))
                    for k in range(8)]
            loops.append({"chain": None, "circle": s, "poly": poly,
                          "area": math.pi * r * r, "bbox": _bbox(poly)})

    # 重复描线去重(v1.35): 完全重合的环只留一个——重复环会被"最小包含
    # 环"逻辑判成第一个环的孔, 材料被错误掏空(AutoCAD 双重描线常见)。
    # 键取环顶点序列的规范化形式(起点取最小顶点+两个绕向取小),
    # 使同一几何的重复环即使链起点不同也能判重。
    def _canon_ring(pts):
        m = min(range(len(pts)), key=lambda t: pts[t])
        r = pts[m:] + pts[:m]
        return tuple((round(x, 3), round(y, 3)) for x, y in r)

    _seen_poly = set()
    _uniq = []
    for lp in loops:
        _p = lp["poly"]
        _k = min(_canon_ring(_p), _canon_ring(_p[::-1]))
        if _k in _seen_poly:
            continue
        _seen_poly.add(_k)
        _uniq.append(lp)
    loops = _uniq

    # 嵌套: 面积降序, 每环找包含它的【最小】外环 → 父子深度
    # v1.29 修复: 过去按 j=0.. 正序扫描(=面积由大到小)取第一个命中, 拿到的
    # 是"最大的包含环" —— 三层嵌套(A⊃B⊃C)时 C 的父环被判成 A 而非 B,
    # depth(C)=1 被当成 A 的第二个孔 → 岛的材料被错误减掉(应独立成体)。
    # 改为 j=i-1.. 逆序扫描(=面积由小到大), 第一个命中即最小包含环,
    # depth(C)=2 → 独立轮廓(下面"岛"分支才真正生效)。
    loops.sort(key=lambda d: -d["area"])
    parent = [-1] * len(loops)
    for i in range(len(loops)):
        bi0, bi1, bi2, bi3 = loops[i]["bbox"]
        for j in range(i - 1, -1, -1):  # j 面积更大; 逆序=先试最小的
            bj0, bj1, bj2, bj3 = loops[j]["bbox"]
            if bi0 >= bj0 and bi1 >= bj1 and bi2 <= bj2 and bi3 <= bj3 \
                    and _loop_in_loop(loops[i]["poly"], loops[j]["poly"]):
                parent[i] = j
                break

    def depth(i):
        d, k = 0, i
        while parent[k] != -1:
            k = parent[k]
            d += 1
        return d

    profiles = []
    for i, lp in enumerate(loops):
        d = depth(i)
        if d % 2 == 0:                      # 偶数层=实体(外轮廓或岛)
            prof = {"outer": lp, "holes": []}
            for k in range(len(loops)):
                if parent[k] == i and depth(k) % 2 == 1:   # 奇数层=孔
                    prof["holes"].append(loops[k])
                # depth 为偶数的子环=岛(体中体), 由它自己的那轮独立成 profile
            profiles.append(prof)
    return profiles, opens, sum(1 for s in segs if s.kind == "circle")


# ============================================================================
# §3 .dlx 对话框生成器(块模板取自本机 NX2312 官方样例 dlx, 见文件尾注释)
# ============================================================================

def _esc(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
             .replace('"', "&quot;"))


def _blk_double(bid, title, value):
    return (
        '<Property class="UICOMP_double" hierarchy="UGS::UICOMP_group" id="{id}" mask="256" '
        'name="{id}" presentation="Double" type="uicomp">'
        '<item Expanded="1" class="UICOMP_double" hierarchy="" icon="styler_real" id="{id}" '
        'name="{id}" notes="" presentation="Double" type="uicomp">'
        '<PropertyList id="id" mode="0">'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_double" id="API Name" '
        'mask="16656" name="API Name" sname="BlockID" source="3" type="string" value="{id}"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_double" id="Visibility" '
        'mask="0" name="Visibility" sname="Show" source="1" type="logical" value="True"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_double" id="Sensitivity" '
        'mask="0" name="Sensitivity" sname="Enable" source="1" type="logical" value="True"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_double" id="Group" '
        'mask="16384" name="Group" sname="Group" source="1" type="logical" value="False"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_double" id="Expanded" '
        'mask="4" name="Expanded" sname="Expanded" source="1" type="logical" value="True"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_double" id="HideGroup" '
        'mask="69636" name="HideGroup" sname="HideGroup" source="1" type="logical" value="False"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_double" id="Focus" '
        'mask="69636" name="Focus" sname="Focus" source="1" type="logical" value="False"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_double" id="CanFocus" '
        'mask="69636" name="CanFocus" sname="CanFocus" source="1" type="logical" value="False"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_double" id="KeyboardFocus" '
        'mask="69636" name="KeyboardFocus" sname="KeyboardFocus" source="1" type="logical" value="False"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_double" id="CanKeyboardFocus" '
        'mask="69636" name="CanKeyboardFocus" source="1" type="logical" value="True"/>'
        '<Property ClassID="UGS::UICOMP_widget" group="Other::" hierarchy="UGS::UICOMP_double" id="ReadWrite" '
        'mask="0" name="ReadWrite" sname="RetainValue" source="1" type="logical" value="False"/>'
        '<Property ClassID="UGS::UICOMP_widget" group="Other::" hierarchy="UGS::UICOMP_double" id="UIOnly" '
        'mask="69636" name="UIOnly" sname="RetainValueInUIOnly" source="1" type="logical" value="False"/>'
        '<Property ClassID="UGS::UICOMP_widget" group="Other::" hierarchy="UGS::UICOMP_double" id="Translated" '
        'mask="16384" name="Translated" sname="Localize" source="1" type="logical" value="True"/>'
        '<Property ClassID="UGS::UICOMP_value" group="Block Specific::" hierarchy="UGS::UICOMP_double" '
        'id="TitleVisibility" mask="0" name="TitleVisibility" sname="TitleVisibility" source="1" '
        'type="logical" value="True"/>'
        '<Property ClassID="UGS::UICOMP_value" group="Block Specific::" hierarchy="UGS::UICOMP_double" '
        'id="UserLockable" mask="69632" name="UserLockable" sname="UserLockable" source="1" '
        'type="logical" value="False"/>'
        '<Property ClassID="UGS::UIFW_spin_options" group="Block Specific::" '
        'hierarchy="UGS::UIFW_spin_options" id="Increment" mask="0" name="Increment" sname="Increment" '
        'source="1" type="double" value="1"/>'
        '<Property ClassID="UGS::UICOMP_value" group="Block Specific::" hierarchy="UGS::UICOMP_double" '
        'id="MinInclusive" mask="4" name="MinInclusive" sname="MinInclusive" source="1" '
        'type="logical" value="True"/>'
        '<Property ClassID="UGS::UICOMP_value" group="Block Specific::" hierarchy="UGS::UICOMP_double" '
        'id="MaxInclusive" mask="4" name="MaxInclusive" sname="MaxInclusive" source="1" '
        'type="logical" value="True"/>'
        '<Property ClassID="UGS::UICOMP_integer" group="Block Specific::" hierarchy="UGS::UICOMP_double" '
        'id="ReadOnlyValue" mask="2" name="ReadOnlyValue" sname="ReadOnlyValue" source="1" '
        'type="logical" value="False"/>'
        '<Property ClassID="UGS::UICOMP_value" group="Block Specific::" hierarchy="UGS::UICOMP_double" '
        'id="RequiredInput" mask="69632" name="RequiredInput" sname="RequiredInput" source="1" '
        'type="logical" value="False"/>'
        '<Property ClassID="UGS::UICOMP_value" group="Block Specific::" hierarchy="UGS::UICOMP_double" '
        'id="AllowUnassignedValue" mask="69632" name="AllowUnassignedValue" sname="AllowUnassignedValue" '
        'source="1" type="logical" value="False"/>'
        '<Property ClassID="UGS::UICOMP_double" group="Block Specific::" hierarchy="UGS::UICOMP_double" '
        'id="VisibleDecimals" mask="69632" name="VisibleDecimals" sname="VisibleDecimals" source="1" '
        'type="integer" value="2"/>'
        '<Property ClassID="UGS::UICOMP_double" group="Block Specific::" hierarchy="UGS::UICOMP_double" '
        'id="MaximumValue" mask="0" name="MaximumValue" sname="MaximumValue" source="1" type="double" '
        'value="1.0E+09"/>'
        '<Property ClassID="UGS::UICOMP_double" group="Block Specific::" hierarchy="UGS::UICOMP_double" '
        'id="LimitCheckTolerance" mask="0" name="LimitCheckTolerance" sname="LimitCheckTolerance" '
        'source="1" type="double" value="-1"/>'
        '<Property ClassID="UGS::UICOMP_double" group="Block Specific::" hierarchy="UGS::UICOMP_double" '
        'id="BalloonTooltipText" mask="0" name="BalloonTooltipText" sname="BalloonTooltipText" source="1" '
        'type="utfstring" value=""/>'
        '<Property ClassID="UGS::UICOMP_double" group="Block Specific::" hierarchy="UGS::UICOMP_double" '
        'id="BalloonTooltipImage" mask="0" name="BalloonTooltipImage" sname="BalloonTooltipImage" '
        'source="1" type="string" value=""/>'
        '<Property ClassID="UGS::UICOMP_double" brief="0" dynamic="0" group="Block Specific::" '
        'hierarchy="UGS::UICOMP_double" id="BalloonTooltipLayout" mask="0" name="BalloonTooltipLayout" '
        'sname="BalloonTooltipLayout" source="1" type="enum" selected="0">'
        '<Option name="Horizontal" value="0"/><Option name="Vertical" value="1"/></Property>'
        '<Property ClassID="UGS::UICOMP_value" brief="0" dynamic="0" group="Block Specific::" '
        'hierarchy="UGS::UICOMP_double" id="PresentationStyle" mask="16640" name="PresentationStyle" '
        'sname="PresentationStyle" source="1" type="enum" selected="0">'
        '<Option name="Keyin" value="0"/><Option name="Spin" value="1"/><Option name="Scale" value="2"/>'
        '<Option name="ScaleKeyin" value="3"/><Option name="Combo" value="4"/></Property>'
        '<Property ClassID="UGS::UICOMP_double" group="Block Specific::" hierarchy="UGS::UICOMP_double" '
        'id="MinimumValue" mask="256" name="MinimumValue" sname="MinimumValue" source="1" type="double" '
        'value="-1.0E+09"/>'
        '<Property ClassID="UGS::UICOMP_double" group="Block Specific::" hierarchy="UGS::UICOMP_double" '
        'id="Value" mask="256" name="Value" sname="Value" source="4" type="double" value="{val}"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_double" id="Title" '
        'mask="256" name="Title" sname="Label" source="1" type="utfstring" value="{title}"/>'
        '<Property ClassID="UGS::UIFW_unit_options" group="Block Specific::" '
        'hierarchy="UGS::UIFW_unit_options" id="ShowUnitLabel" mask="0" name="ShowUnitLabel" '
        'sname="ShowUnitLabel" source="1" type="logical" value="False"/>'
        '<Property ClassID="UGS::UIFW_unit_options" group="Block Specific::" '
        'hierarchy="UGS::UIFW_unit_options" id="AllowUnitEdit" mask="0" name="AllowUnitEdit" '
        'sname="AllowUnitEdit" source="1" type="logical" value="False"/>'
        '</PropertyList></item></Property>'
    ).format(id=bid, title=_esc(title), val=("%.4f" % float(value)).rstrip("0").rstrip(".") or "0")


def _blk_label(bid, text, wrap=True):
    return (
        '<Property class="UICOMP_label" hierarchy="UGS::UICOMP_group" id="{id}" mask="256" '
        'name="{id}" presentation="Label/Bitmap" type="uicomp">'
        '<item Expanded="1" class="UICOMP_label" hierarchy="" icon="styler_label.bmp" id="{id}" '
        'name="{id}" notes="" presentation="Label/Bitmap" type="uicomp">'
        '<PropertyList id="id" mode="0">'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_label" id="API Name" '
        'mask="16400" name="API Name" sname="BlockID" source="3" type="string" value="{id}"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_label" id="Title" '
        'mask="0" name="Title" sname="Label" source="1" type="utfstring" value="{text}"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_label" id="Visibility" '
        'mask="0" name="Visibility" sname="Show" source="1" type="logical" value="True"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_label" id="Sensitivity" '
        'mask="0" name="Sensitivity" sname="Enable" source="1" type="logical" value="True"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_label" id="Group" '
        'mask="16384" name="Group" sname="Group" source="1" type="logical" value="False"/>'
        '<Property ClassID="UGS::UICOMP_widget" group="Other::" hierarchy="UGS::UICOMP_label" id="Translated" '
        'mask="16384" name="Translated" sname="Localize" source="1" type="logical" value="True"/>'
        '<Property ClassID="UGS::UICOMP_label" group="Block Specific::" hierarchy="UGS::UICOMP_label" '
        'id="WordWrap" mask="16384" name="WordWrap" sname="WordWrap" source="1" type="logical" value="%s"/>'
        '</PropertyList></item></Property>'
    ).format(id=bid, text=_esc(text), wrap="True" if wrap else "False")


def _blk_button(bid, title):
    """Action Button 块(模板: ListPointProperties.dlx 的 UICOMP_button)。

    按钮激活经 BlockStyler 的 update 回调送达(block 即该按钮), 处理见
    StdParamsDialog.update_cb / ParamDialog.update_cb。
    """
    return (
        '<Property class="UICOMP_button" hierarchy="UGS::UICOMP_group" id="{id}" mask="256" '
        'name="{id}" presentation="Action Button" type="uicomp">'
        '<item Expanded="1" class="UICOMP_button" hierarchy="UGS::UI::Comp::SuperPoint" '
        'icon="styler_browser_pushbutton.bmp" id="{id}" name="{id}" notes="" '
        'presentation="Action Button" type="uicomp">'
        '<PropertyList id="id" mode="0">'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_button" id="API Name" '
        'mask="16400" name="API Name" sname="BlockID" source="3" type="string" value="{id}"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_button" id="Title" '
        'mask="0" name="Title" sname="Label" source="1" type="utfstring" value="{title}"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_button" id="Visibility" '
        'mask="0" name="Visibility" sname="Show" source="1" type="logical" value="True"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_button" id="Sensitivity" '
        'mask="0" name="Sensitivity" sname="Enable" source="1" type="logical" value="True"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_button" id="Group" '
        'mask="16384" name="Group" sname="Group" source="1" type="logical" value="False"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_button" id="Expanded" '
        'mask="4" name="Expanded" sname="Expanded" source="1" type="logical" value="True"/>'
        '<Property ClassID="UGS::UICOMP" group="Other::" hierarchy="UGS::UICOMP_button" id="UIOnly" '
        'mask="69636" name="UIOnly" sname="RetainValueInUIOnly" source="1" type="logical" value="False"/>'
        '<Property ClassID="UGS::UICOMP" group="Other::" hierarchy="UGS::UICOMP_button" id="Translated" '
        'mask="16384" name="Translated" sname="Localize" source="1" type="logical" value="True"/>'
        '</PropertyList></item></Property>'
    ).format(id=bid, title=_esc(title))


def _blk_filebrowser(bid, title, filt):
    return (
        '<Property class="UGS::UI::Comp::NativeFileBrowser" hierarchy="UGS::UICOMP_group" id="{id}" '
        'mask="256" name="{id}" presentation="File Selection with Browse" type="uicomp">'
        '<item Expanded="1" class="UGS::UI::Comp::NativeFileBrowser" hierarchy="" '
        'icon="report_in_folder.bmp" id="{id}" name="{id}" notes="" '
        'presentation="File Selection with Browse" type="uicomp">'
        '<PropertyList id="id" mode="0">'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UI::Comp::NativeFileBrowser" '
        'id="API Name" mask="16656" name="API Name" sname="BlockID" source="3" type="string" value="{id}"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UI::Comp::NativeFileBrowser" '
        'id="Title" mask="0" name="Title" sname="Label" source="1" type="utfstring" value="{title}"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UI::Comp::NativeFileBrowser" '
        'id="Visibility" mask="0" name="Visibility" sname="Show" source="1" type="logical" value="True"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UI::Comp::NativeFileBrowser" '
        'id="Sensitivity" mask="0" name="Sensitivity" sname="Enable" source="1" type="logical" value="True"/>'
        '<Property ClassID="UGS::UI::Comp::NativeFileSystemBrowser" group="Block Specific::" '
        'hierarchy="UGS::UI::Comp::NativeFileBrowser" id="Path" mask="0" name="Path" sname="Path" '
        'source="3" type="string" value=""/>'
        '<Property ClassID="UGS::UI::Comp::NativeFileSystemBrowser" group="Block Specific::" '
        'hierarchy="UGS::UI::Comp::NativeFileBrowser" id="RetainStringValue" mask="0" '
        'name="RetainStringValue" sname="RetainStringValue" source="1" type="logical" value="True"/>'
        '<Property ClassID="UGS::UI::Comp::NativeFileBrowser" group="Block Specific::" '
        'hierarchy="UGS::UI::Comp::NativeFileBrowser" id="Filter" mask="256" name="Filter" '
        'sname="Filter" source="2" type="string" value="{filt}"/>'
        '</PropertyList></item></Property>'
    ).format(id=bid, title=_esc(title), filt=_esc(filt))


def _blk_enum(bid, title, labels, selected=0):
    """下拉选择块; labels 为中文标签列表, 值由代码按序号映射。"""
    opts = "".join('<Option name="%s" value="%d"/>' % (_esc(t), i)
                   for i, t in enumerate(labels))
    return (
        '<Property class="UICOMP_enum" hierarchy="UGS::UICOMP_group" id="{id}" mask="256" '
        'name="{id}" presentation="Enumeration" type="uicomp">'
        '<item Expanded="1" SupportsDisablingLogic="1" class="UICOMP_enum" hierarchy="" '
        'icon="styler_optionmenu.bmp" id="{id}" name="{id}" notes="" '
        'presentation="Enumeration" type="uicomp">'
        '<PropertyList id="id" mode="0">'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_enum" '
        'id="API Name" mask="16656" name="API Name" sname="BlockID" source="3" type="string" '
        'value="{id}"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_enum" '
        'id="Visibility" mask="0" name="Visibility" sname="Show" source="1" type="logical" '
        'value="True"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_enum" '
        'id="Sensitivity" mask="0" name="Sensitivity" sname="Enable" source="1" '
        'type="logical" value="True"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_enum" '
        'id="Group" mask="16384" name="Group" sname="Group" source="1" type="logical" '
        'value="False"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_enum" '
        'id="Expanded" mask="4" name="Expanded" sname="Expanded" source="1" type="logical" '
        'value="True"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_enum" '
        'id="CanFocus" mask="69636" name="CanFocus" sname="CanFocus" source="1" '
        'type="logical" value="False"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_enum" '
        'id="CanKeyboardFocus" mask="69636" name="CanKeyboardFocus" sname="CanKeyboardFocus" '
        'source="1" type="logical" value="True"/>'
        '<Property ClassID="UGS::UICOMP_widget" group="Other::" hierarchy="UGS::UICOMP_enum" '
        'id="ReadWrite" mask="0" name="ReadWrite" sname="RetainValue" source="1" '
        'type="logical" value="False"/>'
        '<Property ClassID="UGS::UICOMP_widget" group="Other::" hierarchy="UGS::UICOMP_enum" '
        'id="UIOnly" mask="69636" name="UIOnly" sname="RetainValueInUIOnly" source="1" '
        'type="logical" value="False"/>'
        '<Property ClassID="UGS::UICOMP_widget" group="Other::" hierarchy="UGS::UICOMP_enum" '
        'id="Translated" mask="16384" name="Translated" sname="Localize" source="1" '
        'type="logical" value="True"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_enum" '
        'id="TitleVisibility" mask="16384" name="TitleVisibility" sname="LabelVisibility" '
        'source="1" type="logical" value="True"/>'
        '<Property ClassID="UGS::UICOMP_enum" brief="0" dynamic="0" group="Block Specific::" '
        'hierarchy="UGS::UICOMP_enum" id="PresentationStyle" mask="16384" '
        'name="PresentationStyle" sname="PresentationStyle" source="1" type="enum" '
        'selected="0">'
        '<Option name="Option Menu" value="0"/><Option name="Radio Box" value="1"/>'
        '<Option name="Pulldown" value="2"/></Property>'
        '<Property ClassID="UGS::UICOMP_enum" group="Block Specific::" '
        'hierarchy="UGS::UICOMP_enum" id="MaximumValue" mask="69636" name="MaximumValue" '
        'sname="MaximumValue" source="1" type="integer" value="0"/>'
        '<Property ClassID="UGS::UICOMP_enum" group="Block Specific::" '
        'hierarchy="UGS::UICOMP_enum" id="MinimumValue" mask="69636" name="MinimumValue" '
        'sname="MinimumValue" source="1" type="integer" value="0"/>'
        '<Property ClassID="UGS::UICOMP_enum" group="Block Specific::" '
        'hierarchy="UGS::UICOMP_enum" id="Titles" mask="69636" name="Titles" sname="Items" '
        'source="1" type="utfstrings"/>'
        '<Property ClassID="UGS::UICOMP_enum" group="Block Specific::" '
        'hierarchy="UGS::UICOMP_enum" id="Value" mask="69636" name="Value" '
        'sname="TEMPVALUE" source="1" type="integer" value="{sel}"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_enum" '
        'id="Title" mask="257" name="Title" sname="Label" source="1" type="utfstring" '
        'value="{title}"/>'
        '<Property ClassID="UGS::UICOMP_enum" brief="0" dynamic="1" group="Block Specific::" '
        'hierarchy="UGS::UICOMP_enum" id="Titles_1" mask="256" name="Titles_1" '
        'selected="{sel}" sname="Value" source="4" type="enum">{opts}</Property>'
        '</PropertyList></item></Property>'
    ).format(id=bid, title=_esc(title), opts=opts, sel=int(selected))


def _blk_toggle(bid, label, value):
    """复选块(模板取自本机 CheckDeepHoles_Customization.dlx 的 SaveInPart)。"""
    return (
        '<Property class="UICOMP_toggle" hierarchy="UGS::UICOMP_group" id="{id}" mask="256" '
        'name="{id}" presentation="Toggle" type="uicomp">'
        '<item Expanded="1" SupportsDisablingLogic="1" class="UICOMP_toggle" hierarchy="" '
        'icon="styler_toggle.bmp" id="{id}" name="{id}" notes="" presentation="Toggle" '
        'type="uicomp">'
        '<PropertyList id="id" mode="0">'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_toggle" '
        'id="API Name" mask="16656" name="API Name" sname="BlockID" source="3" type="string" '
        'value="{id}"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_toggle" '
        'id="Visibility" mask="0" name="Visibility" sname="Show" source="1" type="logical" '
        'value="True"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_toggle" '
        'id="Sensitivity" mask="0" name="Sensitivity" sname="Enable" source="1" type="logical" '
        'value="True"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_toggle" '
        'id="Group" mask="16384" name="Group" sname="Group" source="1" type="logical" '
        'value="False"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_toggle" '
        'id="Expanded" mask="4" name="Expanded" sname="Expanded" source="1" type="logical" '
        'value="True"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_toggle" '
        'id="HideGroup" mask="69636" name="HideGroup" sname="HideGroup" source="1" '
        'type="logical" value="False"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_toggle" '
        'id="Focus" mask="69636" name="Focus" sname="Focus" source="1" type="logical" '
        'value="False"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_toggle" '
        'id="CanFocus" mask="69636" name="CanFocus" sname="CanFocus" source="1" type="logical" '
        'value="False"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_toggle" '
        'id="KeyboardFocus" mask="69636" name="KeyboardFocus" sname="KeyboardFocus" source="1" '
        'type="logical" value="False"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_toggle" '
        'id="CanKeyboardFocus" mask="69636" name="CanKeyboardFocus" sname="CanKeyboardFocus" '
        'source="1" type="logical" value="True"/>'
        '<Property ClassID="UGS::UICOMP_widget" group="Other::" hierarchy="UGS::UICOMP_toggle" '
        'id="ReadWrite" mask="0" name="ReadWrite" sname="RetainValue" source="1" type="logical" '
        'value="False"/>'
        '<Property ClassID="UGS::UICOMP_widget" group="Other::" hierarchy="UGS::UICOMP_toggle" '
        'id="UIOnly" mask="69636" name="UIOnly" sname="RetainValueInUIOnly" source="1" '
        'type="logical" value="False"/>'
        '<Property ClassID="UGS::UICOMP_widget" group="Other::" hierarchy="UGS::UICOMP_toggle" '
        'id="Translated" mask="16384" name="Translated" sname="Localize" source="1" '
        'type="logical" value="True"/>'
        '<Property ClassID="UGS::UICOMP_toggle" group="Block Specific::" '
        'hierarchy="UGS::UICOMP_toggle" id="Icon" mask="128" name="Icon" sname="Bitmap" '
        'source="3" type="string" value=""/>'
        '<Property ClassID="UGS::UICOMP_toggle" group="Block Specific::" '
        'hierarchy="UGS::UICOMP_toggle" id="BitmapOnly" mask="16384" name="BitmapOnly" '
        'sname="BitmapOnly" source="1" type="logical" value="False"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_toggle" '
        'id="Title" mask="256" name="Title" sname="Label" source="1" type="utfstring" '
        'value="{label}"/>'
        '<Property ClassID="UGS::UICOMP_toggle" group="Block Specific::" '
        'hierarchy="UGS::UICOMP_toggle" id="Value" mask="256" name="Value" sname="Value" '
        'source="4" type="logical" value="{val}"/>'
        '</PropertyList></item></Property>'
    ).format(id=bid, label=_esc(label), val="True" if value else "False")


def build_selection_dlx(files, selected):
    """第一段"标准件选择"对话框: 每个件一个复选框。"""
    children = []
    if not files:
        children.append(_blk_label("sel_hint", "stdparts 目录为空。"))
    for i, f in enumerate(files):
        children.append(_blk_toggle("SEL%d" % i, f, f in selected))
    grp = _group_item("grp_sel", "勾选本次要加载的标准件（新件默认不勾）",
                      "".join(children), columns=1)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<Dialog ContainerItems="1" Expanded="1" NX="2312.0.0" class="" id="Dialog" '
        'languageInfo="Language and Codeset: english 17" name="Dialog" notes="" '
        'title="NX StdPartSelect" type="uicomp" version="1.0.0">'
        + grp +
        '<PropertyList id="id" mode="0">'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::Styler::DialogItem" '
        'id="Title" mask="256" name="Title" sname="Label" source="1" type="utfstring" '
        'value="标准件选择"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::Styler::DialogItem" '
        'id="Cue" mask="256" name="Cue" sname="Cue" source="1" type="utfstring" '
        'value="选择本次要加载的标准件"/>'
        '<Property ClassID="UGS::UICOMP" brief="0" dynamic="0" group="General::Other::" '
        'hierarchy="UGS::Styler::DialogItem" id="NavigationStyle" mask="393472" '
        'name="NavigationStyle" selected="0" sname="Navigation Style" source="1" type="enum">'
        '<Option name="OK Cancel" value="0"/><Option name="Close" value="1"/>'
        '<Option name="OK Apply Cancel" value="2"/></Property>'
        '</PropertyList></Dialog>\n'
    )


def _group_item(gid, title, children_xml, columns=2, collapsed=False):
    return (
        '<item Expanded="{exp}" class="UGS::UICOMP_group" hierarchy="" id="{id}" name="{id}" notes="" '
        'presentation="Group" type="uicomp"><PropertyList>'
        '<Property class="UGS::UI::Comp::Container" dynamic="1" group="Block Specific::" '
        'hierarchy="UGS::UICOMP_group" id="Members" mask="0" name="Members" sname="Members" source="1" '
        'type="array"><PropertyList Expanded="1" class="UGS::UI::Comp::Container" '
        'hierarchy="UGS::UICOMP_group" id="ContainerItems" mode="1">{children}</PropertyList></Property>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_group" id="API Name" '
        'mask="16400" name="API Name" sname="BlockID" source="3" type="string" value="{id}"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_group" id="Title" '
        'mask="1" name="Title" sname="Label" source="1" type="utfstring" value="{title}"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_group" id="Visibility" '
        'mask="0" name="Visibility" sname="Show" source="1" type="logical" value="True"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_group" id="Sensitivity" '
        'mask="0" name="Sensitivity" sname="Enable" source="1" type="logical" value="True"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_group" id="Group" '
        'mask="86020" name="Group" sname="Group" source="1" type="logical" value="True"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_group" id="Expanded" '
        'mask="0" name="Expanded" sname="Expanded" source="2" type="logical" value="{exp}"/>'
        '<Property ClassID="UGS::UICOMP_group" group="Block Specific::" hierarchy="UGS::UICOMP_group" '
        'id="Column" mask="16384" name="Column" sname="Column" source="1" type="integer" value="{col}"/>'
        '</PropertyList></item>'
    ).format(id=gid, title=_esc(title), children=children_xml, col=columns,
            exp=("False" if collapsed else "True"))


def _opt_index(opts, value):
    for i, (v, _t) in enumerate(opts):
        if v == value:
            return i
    return 0


def build_dlx(params=None, jrt=None):
    """从 LAYER_TABLE + JRT 参数生成窗口②完整 .dlx XML(UTF-8)。

    (v1.35) 删除两段式时代的休眠"标准件组"生成——三段式改造后 main 恒以
    无标准件组调用本函数, 标准件参数页由 build_std_dlx(窗口③)负责。
    """
    if params is None:
        params = default_params()
    if jrt is None:
        jrt = dict(DEFAULT_JRT)

    zh = {r[0]: r[1] for r in LAYER_TABLE}

    # 文件组
    g_file = _group_item(
        "grp_file", "输入文件",
        _blk_filebrowser("dxf_file", "DXF 文件", "*.dxf") + _blk_label(
            "hint_label",
            "提示: 起始=结束=0 的图层跳过; LS/RZ/DK 拉伸后从 FLB 减去; "
            "曲线按图层导入到 NX 图层 %d~%d, 特征名前缀 CAD3D_。"
            % (MANAGED_MIN, MANAGED_MAX)),
        columns=1)

    # 参数组(每层两个 double 块: <code>_start / <code>_end)
    groups_xml = []
    for gid, title, codes in DIALOG_GROUPS:
        children = []
        for code in codes:
            s, e = params.get(code, (0.0, 0.0))
            children.append(_blk_double(code + "_start", "%s %s 起始距离" % (code, zh[code]), s))
            children.append(_blk_double(code + "_end", "%s %s 结束距离" % (code, zh[code]), e))
        # v1.21: 单列布局——DialogSizing 无自适应项(实测仅 Allow Resize/
        # Follow Policy)且块模型无宽度属性, 双列行宽超默认窗口被裁;
        # 单列后行宽≈标签+单字段, 默认窗口完整显示。
        groups_xml.append(_group_item(gid, title, "".join(children), columns=1))

    # 加热条组(JRT; 起始==结束 即停用; 区间随 FLB 联动, 底侧自动镜像;
    # 颜色/透明度按期刊固定 186/78/50, 不进界面; 块 id 统一 "jrt_"+key)
    jrt_children = [
        _blk_double("jrt_" + key, label, jrt.get(key, DEFAULT_JRT[key]))
        for key, label in JRT_FIELDS
    ]
    jrt_children.append(_blk_button("jrt_reset", "恢复默认"))
    groups_xml.append(_group_item(
        "grp_jrt", "加热条 JRT（齐平板面/入侵深度/两端倒圆+圆顶；深度0停用）",
        "".join(jrt_children), columns=1))

    dlx = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<Dialog ContainerItems="1" Expanded="1" NX="2312.0.0" class="" id="Dialog" '
        'languageInfo="Language and Codeset: english 17" name="Dialog" notes="" '
        'title="NX FenCengLaShen" type="uicomp" version="1.0.0">'
        + g_file + "".join(groups_xml) +
        '<PropertyList id="id" mode="0">'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::Styler::DialogItem" '
        'id="Title" mask="256" name="Title" sname="Label" source="1" type="utfstring" '
        'value="NX 分层拉伸 (DXF→3D)"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::Styler::DialogItem" '
        'id="Cue" mask="256" name="Cue" sname="Cue" source="1" type="utfstring" '
        'value="设置各图层拉伸参数"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::Styler::DialogItem" '
        'id="Sensitivity" mask="0" name="Sensitivity" sname="Enable" source="1" type="logical" '
        'value="True"/>'
        '<Property ClassID="UGS::UICOMP" brief="0" dynamic="0" group="General::Other::" '
        'hierarchy="UGS::Styler::DialogItem" id="NavigationStyle" mask="393472" name="NavigationStyle" '
        'selected="2" sname="Navigation Style" source="1" type="enum">'
        '<Option name="OK Cancel" value="0"/><Option name="Close" value="1"/>'
        '<Option name="OK Apply Cancel" value="2"/></Property>'
        '</PropertyList></Dialog>\n'
    )
    return dlx


def build_std_dlx(std_rules, params):
    """第三段"标准件参数"对话框: 每件一个可收起组(13 参数块 + Z 基准值标签)。"""
    groups_xml = []
    for i, fname in enumerate(sorted(std_rules)):
        r = std_rules[fname]
        p = "SP%d_" % i
        zval = _std_z(params, r)
        children = [
            _blk_label(p + "zval", "Z基准值: %.4g" % zval),
            _blk_enum(p + "layer", "定位图层",
                      [t for _v, t in LAYER_SEL_OPTS],
                      _opt_index(LAYER_SEL_OPTS, r["layer"])),
        ] + ([]
             if r["layer"] == "CXK" else
             [_blk_double(p + "rmin", "半径min", r["r_min"]),
              _blk_double(p + "rmax", "半径max", r["r_max"])]) + [
            _blk_enum(p + "zmode", "Z基准",
                      [t for _v, t in ZMODE_OPTS],
                      _opt_index(ZMODE_OPTS, r["z_mode"])),
            _blk_double(p + "offx", "X偏移", r["off_x"]),
            _blk_double(p + "offy", "Y偏移", r["off_y"]),
            _blk_double(p + "offz", "Z偏移", r["off_z"]),
            _blk_enum(p + "bool", "布尔",
                      [t for _v, t in BOOL_OPTS],
                      _opt_index(BOOL_OPTS, r["bool_mode"])),
            _blk_enum(p + "dir", "方向",
                      [t for _v, t in DIR_OPTS],
                      _opt_index(DIR_OPTS, r["dir"])),
        ]
        # v1.19: 每件都有恢复默认按钮(无内置默认的件=恢复通用安全默认:
        # 全部图层/全半径/FLB顶/仅放置/+Z/零偏移——压线板一案)
        children.append(_blk_button(p + "reset", "恢复默认"))
        groups_xml.append(_group_item("grp_" + p, fname, "".join(children),
                                      columns=1))   # v1.21 单列; 默认展开
    if not groups_xml:
        groups_xml.append(_group_item("grp_sp_empty", "无选中标准件",
                                      _blk_label("sp_empty_hint",
                                                 "本窗口无参数可设, 直接确定执行。"),
                                      columns=1))

    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<Dialog ContainerItems="1" Expanded="1" NX="2312.0.0" class="" id="Dialog" '
        'languageInfo="Language and Codeset: english 17" name="Dialog" notes="" '
        'title="NX StdParams" type="uicomp" version="1.0.0">'
        + "".join(groups_xml) +
        '<PropertyList id="id" mode="0">'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::Styler::DialogItem" '
        'id="Title" mask="256" name="Title" sname="Label" source="1" type="utfstring" '
        'value="标准件参数"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::Styler::DialogItem" '
        'id="Cue" mask="256" name="Cue" sname="Cue" source="1" type="utfstring" '
        'value="每个标准件一个格子, 点标题展开/收起"/>'
        '<Property ClassID="UGS::UICOMP" brief="0" dynamic="0" group="General::Other::" '
        'hierarchy="UGS::Styler::DialogItem" id="NavigationStyle" mask="393472" '
        'name="NavigationStyle" selected="2" sname="Navigation Style" source="1" type="enum">'
        '<Option name="OK Cancel" value="0"/><Option name="Close" value="1"/>'
        '<Option name="OK Apply Cancel" value="2"/></Property>'
        '</PropertyList></Dialog>\n'
    )


def _logs_dir():
    """运行生成物目录(dlx/日志/调试脚印), 与脚本同级的 logs 子目录。"""
    p = os.path.join(script_dir(), "logs")
    try:
        os.makedirs(p, exist_ok=True)
    except OSError:
        p = script_dir()
    return p


def _fresh_dlx_path(base_name, base_dir=None):
    """唯一 dlx 路径(毫秒戳; 写前清旧)。NX 的对话框记忆按 dlx 文件名
    存取并会在显示时回灌旧值(RetainValue=False 也拦不住, 实测)——
    固定名会让历史会话的错误显示值死灰复燃(v1.17 改回固定名后"标准件
    默认值又丢失错乱"即此); 每轮唯一名让记忆永远无载体。窗口宽度不靠
    文件名记忆(NX 不跨会话记尺寸, 固定名时代用户同样每轮要拉宽),
    由 dlx 内撑宽行直接做够。"""
    d = base_dir if base_dir is not None else _logs_dir()
    try:
        os.makedirs(d, exist_ok=True)
    except OSError:
        pass
    try:
        for n in os.listdir(d):
            if n.endswith(".dlx") and n.startswith(base_name):
                try:
                    os.remove(os.path.join(d, n))
                except OSError:
                    pass
    except OSError:
        pass
    return os.path.join(d, "%s_%d.dlx"
                        % (base_name, int(time.time() * 1000) % 10 ** 10))


def _temp_dlx_path(base_name):
    """%TEMP% 回退路径也用唯一名——固定名会复活 v1.14/v1.17 已根治的
    "NX 按 dlx 文件名回灌旧会话值"事故(v1.35)。"""
    return _fresh_dlx_path(base_name, base_dir=os.environ.get("TEMP") or ".")


def write_std_dlx(std_rules, params):
    """生成第三段 .dlx 到脚本目录(唯一名), 失败回退 %TEMP%(同样唯一名)。"""
    xml = build_std_dlx(std_rules, params)
    candidates = [_fresh_dlx_path("nx_std_params"), _temp_dlx_path("nx_std_params")]
    for path in candidates:
        try:
            with io.open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(xml)
            return path
        except IOError:
            continue
    return None


def write_dlx(params=None, jrt=None):
    """生成窗口② .dlx 到脚本目录(唯一名), 失败回退 %TEMP%(对应 dt:find-dcl 回退链)。"""
    xml = build_dlx(params, jrt)
    candidates = [_fresh_dlx_path("nx_extrude_runner"),
                  _temp_dlx_path("nx_extrude_runner")]
    for path in candidates:
        try:
            with io.open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(xml)
            return path
        except IOError:
            continue
    return None


# ============================================================================
# §4 参数记忆(nx_extrude_params.json)
# ============================================================================

def _json_path():
    return os.path.join(script_dir(), "nx_extrude_params.json")


def load_state():
    p = _json_path()
    try:
        with io.open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        # 坏记忆隔离留证(改名备份), 防止下次 save 用默认值覆盖掉现场
        if os.path.isfile(p):
            try:
                bak = "%s.bad-%s" % (p, time.strftime("%Y%m%d-%H%M%S"))
                os.replace(p, bak)
                _note("nx_extrude_params.json 损坏, 已隔离为 %s, "
                                  "本次按全新记忆处理。" % os.path.basename(bak))
            except OSError:
                pass
        return {}


def _name_list(v):
    """记忆中的文件名列表容错: list/tuple → [str]; 其余(含坏类型)→ []。"""
    if isinstance(v, (list, tuple)):
        return [str(x) for x in v]
    return []


def save_state(dxf_path, params, std_rules=None, selected=None, jrt_se=None):
    """落盘记忆(临时文件+原子替换: 中途崩溃/断电不损原记忆)。

    jrt_se 只存加热条起始/结束两个距离(三个几何参数永不落盘,
    打开恒 3.9/0.1/3.7); 传 None 时原样写 null(=无记忆, 按 FLB 联动)。
    """
    try:
        p = _json_path()
        tmp = "%s.tmp" % p
        with io.open(tmp, "w", encoding="utf-8") as f:
            json.dump({"schema": SCHEMA_VERSION,
                       "dxf_path": dxf_path, "params": params,
                       "std_parts": std_rules or {},
                       "selected": _name_list(selected),
                       "jrt_se": (list(jrt_se)
                                  if isinstance(jrt_se, (list, tuple))
                                  and len(jrt_se) == 2 else None)}, f,
                      ensure_ascii=False, indent=2)
        os.replace(tmp, p)
    except Exception as ex:
        _note("记忆保存失败(%s: %s)。" % (type(ex).__name__, ex))


def merge_params(state):
    """记忆值与默认值合并(记忆优先)。

    schema 门控(v1.35): 版本不符时界面参数(params)一并回默认——与
    config 注释"调大 CONFIG_SCHEMA_VERSION 连界面参数一起回默认"一致。
    """
    out = default_params()
    if not isinstance(state, dict) or state.get("schema") != SCHEMA_VERSION:
        return out
    raw = state.get("params")
    if not isinstance(raw, dict):
        return out                # 坏类型(列表/字符串等)按无记忆处理, 不崩
    for code, v in raw.items():
        if code in out and isinstance(v, (list, tuple)) and len(v) == 2:
            try:
                out[code] = (float(v[0]), float(v[1]))
            except (TypeError, ValueError):
                pass
    return out


def resolve_dxf_path(state):
    """DXF 路径: 记忆值优先, 否则脚本目录最新 *.dxf。"""
    p = state.get("dxf_path") or ""
    if p and os.path.isfile(p):
        return p
    try:
        cands = [os.path.join(script_dir(), n) for n in os.listdir(script_dir())
                 if n.lower().endswith(".dxf")]
        if cands:
            return max(cands, key=os.path.getmtime)
    except OSError:
        pass
    return ""


# ============================================================================
# §5 NX 建模流水线(NXOpen 延迟导入; 批量/自测模式不触发)
# ============================================================================

# 本会话创建的特征登记(名字可能被 NX 自动改尾号导致前缀清理漏网, 双保险)
_CREATED_FEATURES = []

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


def _q(v, nd=4):
    return round(float(v), nd)


def _nx_curve_fp(c):
    """NX 曲线 → 几何指纹(线=两端点; 弧=圆心,半径,起终角)。取不到返回 None。"""
    tname = type(c).__name__
    try:
        if tname == "Line":
            a, b = c.StartPoint, c.EndPoint
            p1, p2 = (_q(a.X), _q(a.Y)), (_q(b.X), _q(b.Y))
            return ("L",) + tuple(sorted((p1, p2)))
        if tname == "Arc":
            ctr = c.CenterPoint
            return ("A", _q(ctr.X), _q(ctr.Y), _q(c.Radius),
                    _q(c.StartAngle, 6), _q(c.EndAngle, 6))
    except Exception:
        return None
    return None


def _dxf_ent_fp(e):
    """DXF 实体 → 几何指纹(与 _nx_curve_fp 同一套量化, 可互相匹配)。"""
    if e.kind == "line":
        p1, p2 = (_q(e.p1[0]), _q(e.p1[1])), (_q(e.p2[0]), _q(e.p2[1]))
        return ("L",) + tuple(sorted((p1, p2)))
    if e.kind == "arc":
        return ("A", _q(e.c[0]), _q(e.c[1]), _q(e.r), _q(e.a0, 6), _q(e.a1, 6))
    # circle → 整圆弧(0..2π), 与 create_curves 的建法一致
    return ("A", _q(e.c[0]), _q(e.c[1]), _q(e.r), 0.0, round(2 * math.pi, 6))


def dxf_fingerprints(layers):
    """全部 DXF 实体的指纹多重集(旧版无标记曲线的迁移匹配用)。"""
    from collections import Counter
    fps = Counter()
    for ents in (layers or {}).values():
        for e in ents:
            fp = _dxf_ent_fp(e)
            if fp is not None:
                fps[fp] += 1
    return fps


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


def nx_purge(session, work_part, log, dxf_layers=None):
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
    """
    global NXOpen
    feats, curves, comps = [], [], []
    try:
        for f in _iter(work_part.Features):
            if str(getattr(f, "Name", "")).startswith(FEATURE_PREFIX):
                feats.append(f)
    except Exception as ex:
        log("【清理】特征枚举失败: %s" % ex)
    for f in list(_CREATED_FEATURES):               # 登记表双保险(仅本工作部件)
        try:
            if f not in feats and f.OwningPart == work_part:
                feats.append(f)
        except Exception:
            pass
    del _CREATED_FEATURES[:]
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
                session.SetUndoMark(NXOpen.Session.MarkVisibility.Invisible, "CAD3D 清理"))
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
                session.SetUndoMark(NXOpen.Session.MarkVisibility.Invisible, "CAD3D 清理体"))
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
            bldr.Offset.StartOffset.SetFormula(_fmt_num(offset[0]))
            bldr.Offset.EndOffset.SetFormula(_fmt_num(offset[1]))
        if draft is not None:
            bldr.Draft.FrontDraftAngle.SetFormula(_fmt_num(draft))
            bldr.Draft.BackDraftAngle.SetFormula(_fmt_num(draft))
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
        _CREATED_FEATURES.append(feat)
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


def _place_delta(ref, flip, off):
    """(纯逻辑)放置位移: basePoint = 锚点 + 本函数返回值。

    basePoint = 锚点 − R·ref + off(R 为插入姿态矩阵):
      +Z(R=I)      → (−ref_x+ox, −ref_y+oy, −ref_z+oz)
      -Z(绕X 180°) → ref 的 y/z 分量随零件坐标系翻转反号——此前直接用
                     −ref, 翻转件对位误差 = (0, 2·ref_y, 2·ref_z)(v1.35 修复)
    """
    rx = _cfg_num(ref[0], 0.0)
    ry = _cfg_num(ref[1], 0.0)
    rz = _cfg_num(ref[2], 0.0)
    ox = _cfg_num(off[0], 0.0)
    oy = _cfg_num(off[1], 0.0)
    oz = _cfg_num(off[2], 0.0)
    if flip:
        ry, rz = -ry, -rz
    return (-rx + ox, -ry + oy, -rz + oz)




def _center_seen(grid, x, y, tol=LOOP_TOL):
    """量化网格 + 3×3 邻桶判同心: 已见返回 True, 未见登记并返回 False。

    (v1.35) 替代对 found 的 O(n²) 线性 any() 扫描——"空图层+全半径"配错
    时上万圆心的去重曾先行卡死, 护栏来不及救。
    """
    kx, ky = int(round(x / tol)), int(round(y / tol))
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            for px, py in grid.get((kx + dx, ky + dy), ()):
                if abs(px - x) < tol and abs(py - y) < tol:
                    return True
    grid.setdefault((kx, ky), []).append((x, y))
    return False


def collect_circle_anchors(layers, rule):
    """规则筛选圆/圆弧圆心 → [(cx, cy, r)]; 同心去重。

    v1.10: 定位图层=CXK 时改为"线中点"锚点——2D 图 CXK 层只画一条线,
    中点即放置点(接线盒规则; 半径字段对该层无意义, 忽略)。
    """
    lay = rule.get("layer") or ""
    if lay == "CXK":
        found, grid = [], {}
        for e in (layers.get("CXK") or []):
            if e.kind == "line":
                mx = (e.p1[0] + e.p2[0]) / 2.0
                my = (e.p1[1] + e.p2[1]) / 2.0
                if not _center_seen(grid, mx, my):
                    found.append((mx, my, 0.0))
        return found
    codes = [lay] if lay else LAYER_CODES
    rmin, rmax = rule["r_min"], rule["r_max"]
    found, grid = [], {}
    for code in codes:
        for e in (layers.get(code) or []):
            if e.kind in ("circle", "arc") and (rmin - 1e-9) <= e.r <= (rmax + 1e-9):
                c = e.c
                if not _center_seen(grid, c[0], c[1]):
                    found.append((c[0], c[1], e.r))
    return found


def _std_z(params, rule):
    """插入点 Z = z_mode 查 ZMODE_DEFS 选出的基准面 + off_z。

    负区间也正确(top=max, bottom=min)。查不到的 z_mode(如旧 json 的
    ABS)回 FLB 顶面。
    """
    zm = rule["z_mode"]
    for _k, _lbl, layer, side in _ZMODE_DEFS:
        if _k == zm:
            s, e = params.get(layer, (0.0, 0.0))
            base = max(s, e) if side == "TOP" else min(s, e)
            return base + rule["off_z"]
    s, e = params.get(TARGET_CODE, (0.0, 0.0))
    return max(s, e) + rule["off_z"]


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
            _CREATED_FEATURES.append(feat)
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
        _CREATED_FEATURES.append(f)
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
    del _CREATED_FEATURES[:]          # 特征已无, 登记表清空
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
                    session.SetUndoMark(NXOpen.Session.MarkVisibility.Invisible,
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
                                        NXOpen.Session.MarkVisibility.Invisible,
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
        _CREATED_FEATURES.append(feat)
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
        _CREATED_FEATURES.append(feat)
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
    """主流水线: 清理 → 建曲线 → 分层拉伸/布尔。返回 (ok, stats)。"""
    global NXOpen
    import NXOpen as _nx
    import NXOpen.Features             # 子模块显式导入(交互期刊不会自动挂包属性)
    import NXOpen.GeometricUtilities
    NXOpen = _nx

    if session is None:
        session = _nx.Session.GetSession()
    if work_part is None:
        work_part = session.Parts.Work
    if log is None:
        log = Log(session)
    stats = {}

    log("")
    log("================ NX 分层拉伸 v%s ================" % SCRIPT_VERSION)
    for _note in _CFG_NOTES:
        log("【配置提示】%s" % _note)
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
        nx_purge(session, work_part, log, dxf_layers=layers)

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
            self.theDialog.Launch()
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
                     std_rules_all=None, selected=None, ui=None):
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
               jrt_se=[jrt.get("start", 0.0), jrt.get("end", 0.0)])
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
        self._shown = False
        self._initializing = False

    # ---------- 辅助 ----------
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
        """FLB 起始/结束任一变动 → 按 LINK_RULES 实时刷新 LS/RZ/DK/DP 与 JRT
        (联动后各层仍可单独修改; 再改 FLB 会再次覆盖)。"""
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
            flb_s = self._find("FLB_start")
            flb_e = self._find("FLB_end")
            if block in (flb_s, flb_e):
                s = self._get_double("FLB_start", 0.0)
                e = self._get_double("FLB_end", 0.0)
                linked = derive_linked(max(s, e), min(s, e))
                for code, (v1, v2) in linked.items():
                    for suffix, val in (("_start", v1), ("_end", v2)):
                        bid = ("jrt" if code == "JRT" else code) + suffix
                        try:
                            self._find(bid).Value = val
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
        return 0

    def _collect(self):
        params = {}
        for code in LAYER_CODES:
            d_s, d_e = self.params[code]
            s = self._get_double(code + "_start", d_s)
            e = self._get_double(code + "_end", d_e)
            params[code] = (s, e)
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
            return 0
        std_rules = self._collect_std()
        self.params = params
        self.std_rules = std_rules
        self.jrt = jrt
        ok = execute_pipeline(dxf, params, jrt, std_rules, self.theSession,
                              std_rules_all=self.std_rules_all,
                              selected=self.selected, ui=self.theUI)
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
            return self.theDialog.Launch()
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
                 std_rules_all=None):
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
                                  selected=self.selected, ui=self.theUI)
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
            return self.theDialog.Launch()
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

def make_sample_dxf(path):
    """生成 7 图层合成测试 DXF(覆盖: 多环/圆/嵌套垫片/贯穿 subtract)。"""

    def rect(layer, x, y, w, h):
        out = []
        for (x1, y1, x2, y2) in [(x, y, x + w, y), (x + w, y, x + w, y + h),
                                 (x + w, y + h, x, y + h), (x, y + h, x, y)]:
            out += ["0", "LINE", "8", layer, "10", "%.3f" % x1, "20", "%.3f" % y1,
                    "30", "0", "11", "%.3f" % x2, "21", "%.3f" % y2, "31", "0"]
        return out

    def circle(layer, cx, cy, r):
        return ["0", "CIRCLE", "8", layer, "10", "%.3f" % cx, "20", "%.3f" % cy,
                "30", "0", "40", "%.3f" % r]

    body = ["0", "SECTION", "2", "ENTITIES"]
    body += rect("FLB", 0, 0, 200, 40)        # 通道 1
    body += rect("FLB", 0, 80, 200, 40)       # 通道 2(多体 unite 场景)
    body += rect("JT", 250, 0, 120, 60)
    for (cx, cy) in [(10, 10), (190, 10), (10, 30), (190, 30)]:
        body += circle("LS", cx, cy, 4.25)
    body += circle("RZ", 100, 20, 11.35)
    body += circle("DK", 100, 20, 3.0)        # 与 RZ 同心(嵌套 subtract 场景)
    body += circle("RZ", 100, 100, 11.35)
    body += circle("DK", 100, 100, 3.0)
    body += rect("DP", 0, -80, 60, 60)        # 垫片外环
    body += rect("DP", 10, -70, 40, 40)       # 垫片内环(同层嵌套→孔)
    body += rect("CX", 0, 160, 30, 10)
    body += rect("JRT", 0, 220, 120, 30)     # 参考图层(只导入不拉伸)
    body += ["0", "LINE", "8", "LD", "10", "0", "20", "-30", "30", "0",
             "11", "0", "21", "-31", "31", "0"]   # 动态分配图层的参考线
    body += ["0", "ENDSEC", "0", "EOF"]

    with io.open(path, "w", encoding="ascii", newline="\n") as f:
        f.write("\n".join(body))
    return path


def _undefined_name_check(path):
    """AST 静态检查: 模块内所有 Name 引用是否可解析(模块级/内建/作用域链)。

    捕捉"交互路径才炸"的拼写 NameError(教训: build_selection_dxl 笔误,
    批量冒烟走不到 main() 交互路径未暴露)。嵌套函数可见外层局部名;
    global 声明的名视为已解析(可能在别处赋值)。
    """
    import ast
    import builtins

    with io.open(path, "r", encoding="utf-8") as f:
        tree = ast.parse(f.read())

    module_names = set(dir(builtins)) | {"__name__", "__file__"}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            module_names.add(node.name)
        elif isinstance(node, ast.Import):
            for a in node.names:
                module_names.add(a.asname or a.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for a in node.names:
                module_names.add(a.asname or a.name)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                for n in ast.walk(t):
                    if isinstance(n, ast.Name):
                        module_names.add(n.id)

    bad = []

    def fn_locals(fn):
        local = set()
        globs = set()
        for n in ast.walk(fn):
            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store):
                local.add(n.id)
            elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef,
                                ast.ClassDef)):
                local.add(n.name)   # 函数内定义的类同样绑定局部名(v1.35)
            elif isinstance(n, ast.arg):
                local.add(n.arg)
            elif isinstance(n, ast.ExceptHandler) and n.name:
                local.add(n.name)
            elif isinstance(n, ast.Import):
                for a in n.names:
                    local.add(a.asname or a.name.split(".")[0])
            elif isinstance(n, ast.ImportFrom):
                for a in n.names:
                    local.add(a.asname or a.name)
            elif isinstance(n, ast.Global):
                globs.update(n.names)
        return local, globs

    def visit_fn(fn, enclosing):
        local, globs = fn_locals(fn)
        visible = enclosing | local | globs
        for n in ast.walk(fn):
            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load) \
                    and n.id not in visible:
                bad.append("line %d: %s" % (n.lineno, n.id))
        for child in ast.walk(fn):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                    and child is not fn:
                visit_fn(child, visible)

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            visit_fn(node, module_names)
    return bad



def selftest(dxf_path=None):
    import xml.etree.ElementTree as ET        # dlx 良构校验(全函数共用)

    ok = True

    def check(name, cond, extra=""):
        nonlocal ok
        print("[%s] %s %s" % ("PASS" if cond else "FAIL", name, extra))
        if not cond:
            ok = False

    for _note in _CFG_NOTES:       # 配置缺失/损坏在这里可见, 不静默回退
        print("[INFO] 配置提示: %s" % _note)

    # 0. AST 未定义名称检查(防交互路径 NameError; 改名/删函数后必查)
    _src = os.path.join(script_dir(), "nx_extrude_runner.py")
    if os.path.isfile(_src):
        bad_names = _undefined_name_check(_src)
        check("AST 未定义名称=0", not bad_names, "; ".join(bad_names[:6]))

    # 1. 链环: 闭合矩形
    segs = [DXLine((0, 0), (10, 0)), DXLine((10, 0), (10, 5)),
            DXLine((10, 5), (0, 5)), DXLine((0, 5), (0, 0))]
    closed, opens = find_chains(segs)
    check("矩形闭链", len(closed) == 1 and not opens)

    # 2. 开口链
    segs2 = segs[:3]
    closed2, opens2 = find_chains(segs2)
    check("开口链检测", not closed2 and len(opens2) == 1)

    # 3. 嵌套: 外方 + 内方 → 1 轮廓带 1 孔
    outer = [DXLine((0, 0), (100, 0)), DXLine((100, 0), (100, 100)),
             DXLine((100, 100), (0, 100)), DXLine((0, 100), (0, 0))]
    inner = [DXLine((40, 40), (60, 40)), DXLine((60, 40), (60, 60)),
             DXLine((60, 60), (40, 60)), DXLine((40, 60), (40, 40))]
    profs, opens3, _ = organize_loops(outer + inner)
    check("嵌套→孔", len(profs) == 1 and len(profs[0]["holes"]) == 1,
          "profiles=%d holes=%d" % (len(profs), len(profs[0]["holes"]) if profs else -1))

    # 3b. 三层嵌套(孔中岛): 岛须独立成体, 不能当成第二个孔被减掉
    #     (v1.29 修复: parent 取"最小包含环"; 此前取到最大环→岛被判成 A 的
    #      第二个孔, 岛的材料被一并减掉, 与 2D 图不符)
    def _sq(x, y, w, h):
        return [DXLine((x, y), (x + w, y)), DXLine((x + w, y), (x + w, y + h)),
                DXLine((x + w, y + h), (x, y + h)), DXLine((x, y + h), (x, y))]

    _A, _B, _C = _sq(0, 0, 100, 100), _sq(20, 20, 60, 60), _sq(40, 40, 20, 20)
    profs3b, _o3b, _ = organize_loops(_A + _B + _C)
    check("三层嵌套: 岛独立成轮廓(不并进孔)",
          len(profs3b) == 2 and len(profs3b[0]["holes"]) == 1
          and not profs3b[1]["holes"]
          and profs3b[0]["outer"]["bbox"] == (0, 0, 100, 100)
          and profs3b[1]["outer"]["bbox"] == (40, 40, 60, 60),
          "profiles=%d" % len(profs3b))
    # 3c. 四层嵌套: 外环带1孔 + 岛再带1孔
    _D = _sq(10, 10, 80, 80)
    profs3c, _o3c, _ = organize_loops(_A + _D + _B + _C)
    check("四层嵌套: 外带1孔 + 岛带1孔",
          len(profs3c) == 2 and len(profs3c[0]["holes"]) == 1
          and len(profs3c[1]["holes"]) == 1
          and profs3c[1]["outer"]["bbox"] == (20, 20, 80, 80),
          "profiles=%d" % len(profs3c))

    # 4. 圆独立轮廓 + 弧参与闭环
    arc_ring = [DXArc((50, 50), 20, 0, math.pi), DXArc((50, 50), 20, math.pi, 2 * math.pi)]
    profs4, _o4, nc4 = organize_loops(arc_ring + [DXCircle((0, 0), 5)])
    check("两半弧成环 + 圆轮廓", len(profs4) == 2)

    # 5. 合成 DXF 解析
    sample = os.path.join(script_dir(), ".zcode", "sample_layers.dxf")
    try:
        os.makedirs(os.path.dirname(sample), exist_ok=True)
    except OSError:
        pass
    make_sample_dxf(sample)
    layers, stats = parse_dxf(sample)
    check("合成 DXF 各层曲线数",
          len(layers.get("FLB", [])) == 8 and len(layers.get("LS", [])) == 4
          and len(layers.get("DP", [])) == 8 and len(layers.get("RZ", [])) == 2,
          str({k: len(v) for k, v in layers.items()}))
    check("JRT 参考图层导入", len(layers.get("JRT", [])) == 4)
    check("LD 参考图层导入", len(layers.get("LD", [])) == 1)
    mp = assign_layers(["LD", "0", "FLB", "JRT"])
    check("动态图层号分配", mp["FLB"] == _cfg("NX_LAYER_START", 11)
          and mp["JRT"] == _cfg("NX_LAYER_JRT", 18)
          and mp["0"] == _cfg("NX_LAYER_DYNAMIC_START", 19)
          and mp["LD"] == _cfg("NX_LAYER_DYNAMIC_START", 19) + 1,
          str(mp))
    _lo_cfg = _cfg("LINK_OFFSETS", {})
    if not isinstance(_lo_cfg, dict):
        _lo_cfg = {}
    check("联动/JRT建模/图层号均来自 config(v1.33)",
          _LINK_OFFSETS == {k: _cfg_num(_lo_cfg.get(k), d)
                            for k, d in (("RZ", 13.0), ("DK", 3.0),
                                         ("DP", 6.7023))}
          and JRT_FROM_TOP == _cfg_num(_cfg("JRT_INTRUSION_DEFAULT", 7.5), 7.5)
          and DEFAULT_JRT["offset"] == _cfg_num(_cfg("JRT_OFFSET", 5.0), 5.0)
          and DEFAULT_JRT["draft"] == _cfg_num(_cfg("JRT_DRAFT", 2.0), 2.0)
          and DEFAULT_JRT["color_strip"] == _cfg_int("JRT_COLOR_STRIP", 186)
          and MANAGED_MAX == _cfg_int("NX_LAYER_MAX", 70)
          and STDPARTS_DIRNAME == _cfg("STDPARTS_DIRNAME", "stdparts"))

    # 6. 几何指纹(清理迁移匹配的纯逻辑部分)
    fp_line = _dxf_ent_fp(DXLine((10.00004, 20.0), (10.0, 25.0)))
    fp_line2 = _dxf_ent_fp(DXLine((10.0, 25.0), (10.00004, 20.0)))
    check("线指纹与端点顺序无关", fp_line == fp_line2)
    fp_c = _dxf_ent_fp(DXCircle((5, 5), 3))
    fp_a = _dxf_ent_fp(DXArc((5, 5), 3, 0.0, 2 * math.pi))
    check("圆指纹=整圆弧指纹(与建法一致)", fp_c == fp_a, "%s vs %s" % (fp_c, fp_a))
    fps = dxf_fingerprints({"X": [DXLine((0, 0), (1, 1)), DXCircle((2, 2), 1)]})
    check("指纹多重集", fps.get(fp_line, 0) == 0 and
          fps.get(("L", (0.0, 0.0), (1.0, 1.0)), 0) == 1 and
          fps.get(_dxf_ent_fp(DXCircle((2, 2), 1)), 0) == 1)

    # 7. JRT 侧向区间(纯逻辑; 新签名 start/end + 底侧镜像)
    sides = _jrt_sides(-40.0, -47.5, -85.0)
    check("JRT 两侧区间(负 Z)",
          sides == [("T", -40.0, -47.5), ("B", -85.0, -77.5)], str(sides))
    sides2 = _jrt_sides(45.0, 37.5, 0.0)
    check("JRT 两侧区间(正 Z)",
          sides2 == [("T", 45.0, 37.5), ("B", 0.0, 7.5)], str(sides2))
    # v1.9: JRT 恒默认不持久化(JSON 漂移污染的根治; start/end 由 FLB 联动)
    jx = merge_jrt({"jrt": {"start": "5", "end": -2.5, "blend_r": 3.8}})
    check("JRT 不读记忆(恒默认)", jx == dict(DEFAULT_JRT), str(jx))
    check("JRT 默认值 3.9/0.1/3.7",
          DEFAULT_JRT["blend_r"] == 3.9 and DEFAULT_JRT["r_step"] == 0.1
          and DEFAULT_JRT["r_min"] == 3.7)

    # 7b. FLB 联动推导
    d = derive_linked(-40.0, -90.0)
    check("联动推导 FLB(-40,-90)",
          d["LS"] == (-40.0, -90.0) and d["RZ"] == (-77.0, -90.0)
          and d["DK"] == (-40.0, -43.0)
          and abs(d["DP"][0] - -83.2977) < 1e-9 and d["DP"][1] == -90.0
          and d["JRT"] == (-40.0, -47.5), str(d))
    d2 = derive_linked(45.0, 0.0)
    check("联动推导 正 Z 参数",
          d2["RZ"] == (13.0, 0.0) and d2["DK"] == (45.0, 42.0)
          and d2["DP"] == (6.7023, 0.0) and d2["JRT"] == (45.0, 37.5))

    # 7c. enum Value 属性写入选中序号(修复"全部卡第0项"的关键)
    en = _blk_enum("t", "测试", ["甲", "乙", "丙"], 2)
    check("enum Value=选中序号", 'sname="TEMPVALUE" source="1" type="integer" value="2"'
          in en)
    # dlx 加热条组
    xml3 = build_dlx(default_params(), dict(DEFAULT_JRT))
    try:
        ET.fromstring(xml3)
        check("带 JRT dlx 良构", True)
    except ET.ParseError as ex:
        check("带 JRT dlx 良构", False, str(ex))
    check("dlx jrt 块数=5+重置按钮",
          xml3.count('type="string" value="jrt_') == 6
          and 'id="jrt_reset"' in xml3)
    check("RetainValue 全 False(防跨窗保留污染)",
          'sname="RetainValue" source="1" type="logical" value="True"' not in xml3)
    for _nm, _xx in (("标准件参数dlx", build_std_dlx({}, default_params())),
                     ("选件dlx", build_selection_dlx(["a.prt"], []))):
        check("RetainValue False(%s)" % _nm,
              'sname="RetainValue" source="1" type="logical" value="True"'
              not in _xx)
    _fp = _fresh_dlx_path("selftest_dlx")
    check("dlx 唯一名( NX 旧值记忆无载体)",
          "selftest_dlx_" in os.path.basename(_fp)
          and not os.path.isfile(_fp))

    # id 往返校验(v1.6 教训: dlx 块 id 与收集构造不一致 → 参数永远失效)
    for key, _label in JRT_FIELDS:
        check("JRT id 往返 jrt_%s" % key,
              ('value="jrt_%s"' % key) in xml3)
    # 7d. 标准件规则引擎(纯逻辑; v1.9 默认值表驱动)
    g1 = guess_std_rule("垫片.prt")
    check("猜测: 垫片→DK/FLB顶/放置+减去", g1["layer"] == "DK"
          and g1["z_mode"] == "FLB_TOP" and g1["bool_mode"] == "PLACE_SUBTRACT")
    g2 = guess_std_rule("大水口-25.prt")
    check("猜测: 大水口→RZ/FLB底", g2["layer"] == "RZ"
          and g2["z_mode"] == "FLB_BOTTOM")
    g3 = guess_std_rule("LS-45.prt")
    check("猜测: LS-→LS/FLB顶/放置+减去", g3["layer"] == "LS"
          and g3["z_mode"] == "FLB_TOP"
          and g3["bool_mode"] == "PLACE_SUBTRACT")
    g4 = guess_std_rule("主进胶与中心定位垫片-30.prt")
    check("猜测: 主进胶优先于垫片/DP/FLB底/放置+减去",
          g4["layer"] == "DP" and g4["z_mode"] == "FLB_BOTTOM"
          and g4["bool_mode"] == "PLACE_SUBTRACT")
    check("旧字段已删(bool_body/ref_*/anchor)",
          "bool_body" not in g3 and "ref_x" not in g3 and "anchor" not in g3)
    g7 = guess_std_rule("接线盒-24针.prt")
    check("猜测: 接线盒→CXK线中点/CX顶值/仅放置",
          g7["layer"] == "CXK" and g7["z_mode"] == "CX_TOP"
          and g7["bool_mode"] == "PLACE")
    check("CXK 在图层选项且规则合法",
          "CXK" in [v for v, _t in LAYER_SEL_OPTS]
          and sanitize_std_rule({"layer": "cxk"})["layer"] == "CXK")
    lay_k = {"CXK": [DXLine((4508.8388106206, 1791.264313510919),
                           (4543.782447818045, 1789.27881120337))]}
    ak = collect_circle_anchors(lay_k, sanitize_std_rule({"layer": "CXK"}))
    check("CXK 线中点锚点≈(4526.31,1790.27)(3Dtest 实线)",
          len(ak) == 1 and abs(ak[0][0] - 4526.3106) < 0.01
          and abs(ak[0][1] - 1790.2716) < 0.01, str(ak))
    # CX+CXK 合并闭环(2D 新规则: CX 单独开口, CXK 补线成环)
    cx_open = [DXLine((0, 0), (10, 0)), DXLine((10, 0), (10, 5)),
               DXLine((10, 5), (0, 5))]
    lay_m = {"CX": cx_open, "CXK": [DXLine((0, 5), (0, 0))]}
    me = modeling_ents(lay_m, "CX")
    profs_m, opens_m, _ = organize_loops(me)
    check("CX+CXK 并入成环", len(me) == 4 and len(profs_m) == 1 and not opens_m)
    check("非 CX 层不并入 CXK",
          len(modeling_ents({"JT": cx_open, "CXK": lay_m["CXK"]}, "JT")) == 3)
    # 顶面靠后边缘中点(纯逻辑; 三型号实测面数据回放)
    # v1.15 防卡死护栏(nx_std_config.STD_MAX_ANCHORS + 特征指纹)
    check("护栏: 数量超限", anchors_overflow(
        list(range(201)), sanitize_std_rule({})))
    check("护栏: 正常数量不超限", not anchors_overflow(
        list(range(8)), sanitize_std_rule({"layer": "LS", "r_max": 5})))
    check("护栏: 空图层+大半径=指纹拦截(卡死案规则)",
          anchors_overflow(list(range(47)),
                           sanitize_std_rule({"layer": "", "r_max": 9999})))
    # v1.17 开链修复(123.dxf: 0.24mm 接缝两条链该合并; 25mm 缺口该桥接)
    _oe = [DXLine((0, 0), (10, 0)), DXLine((10, 0), (10, 5)),
           DXLine((10, 5), (0, 5)),                       # 链1: 缺左边(断口(0,0),(0,5))
           DXLine((0, 5.2), (0.2, 5.2)), DXLine((0.2, 5.2), (0.2, 0.2)),
           DXLine((0.2, 0.2), (0, 0.2))]                  # 链2 三段折线, 断口(0,5.2),(0,0.2)
    _ce, _bj, _ol = _merge_open_chains(
        [[(0, False), (1, False), (2, False)],
         [(3, False), (4, False), (5, False)]], _oe, tol=0.5, bridge_max=0.5)
    check("开链修复: 近缝两链合并→2条接缝桥(≤0.5)",
          len(_ce) == 0 and len(_bj) == 1 and len(_bj[0][1]) == 2, str(_bj))
    _e2 = [DXLine((0, 0), (10, 0)), DXLine((10, 0), (10, 5)),
           DXLine((10, 5), (0, 5))]                        # 缺 10mm 左边
    _ce2, _bj2, _ol2 = _merge_open_chains([[(0, False), (1, False), (2, False)]],
                                          _e2, tol=0.5)
    check("开链修复: 5mm 缺口→放弃记日志(直线桥大缺口=怪条一案)",
          not _ce2 and not _bj2 and len(_ol2) == 1, str((_ce2, _bj2, _ol2)))
    _ce3, _bj3, _ol3 = _merge_open_chains([[(0, False)]], [DXLine((0, 0), (10, 0))],
                                          tol=0.5)
    check("开链修复: 10mm 缺口→放弃", len(_bj3) == 0 and len(_ol3) == 1)
    # 泛化: 1 接缝簇 + 2 单点簇(3Dtest 实际形态)→ 2 条桥全闭合
    _e5 = [DXLine((0, 0), (10, 0)), DXLine((10, 0), (10, 5)),
           DXLine((10, 5), (10, 5.065)), DXLine((10, 5.065), (0, 5.065)),
           DXLine((0, 0.2), (0, 4.8))]     # 右上0.065接缝 + 左边缺0.2~4.8
    _ce5, _bj5, _ol5 = _merge_open_chains(
        [[(0, False), (1, False), (2, False), (3, False), (4, False)]],
        _e5, tol=0.5)
    check("开链修复: 两处小缝(0.2/0.265)→2桥闭合",
          not _ce5 and len(_bj5) == 1 and len(_bj5[0][1]) == 2
          and not _ol5, str(_bj5))
    _ce4, _bj4, _ol4 = _merge_open_chains(
        [[(0, False), (1, False), (2, False), (3, False)]],
        [DXLine((0, 0), (5, 0)), DXLine((6, 0), (10, 0)),
         DXLine((0, 1), (5, 1)), DXLine((6, 1), (10, 1))], tol=0.5)
    check("开链修复: 断口>2簇→放弃记日志",
          not _ce4 and not _bj4 and len(_ol4) == 1)
    # v1.17 倒圆异形检测(体积校验)
    check("_blend_ok: 丢体11%=正常(基准样板实证)",
          _blend_ok(41049.5, 36553.8))
    # v1.23 面体检(jrt1 好条=全解析; 01 坏条=样条面/碎片面)
    _good_rows = [(16, 3.9, 0), (19, 25.1, 0), (22, 0.0, 1),
                  (18, 0.0, 0)]
    _bad_rows = _good_rows + [(20, 0.0, 0), (23, 3.9, 0)]
    _sliver = _good_rows + [(22, 0.0, 2)]
    check("面体检: 好条全解析→通过", _faces_healthy(_good_rows)[0])
    check("面体检: 样条面不算异形(v1.24, 样条墙正常产物)",
          _faces_healthy(_bad_rows)[0])
    check("面体检: 零尺寸碎片→异形", not _faces_healthy(_sliver)[0]
          and "碎片" in _faces_healthy(_sliver)[1])
    check("_blend_ok: 丢体>25%=异形", not _blend_ok(100.0, 74.0))
    check("_blend_ok: 体积0=异形", not _blend_ok(100.0, 0.0))
    check("_blend_ok: 测不到不拦", _blend_ok(None, None))
    # v1.17 删面收紧(圆柱面半径匹配+距离门控; 期刊面中心距连接线≈1)
    _rows = [(1, 10.0, 10.0, 3.9), (2, 10.0, 40.0, 3.9), (3, 50.0, 10.0, 3.9),
             (4, 10.0, 10.0, 300.0)]                    # 第4个=巨R非倒圆面
    check("删面: 半径匹配+距离近→选中",
          _conn_face_pick(_rows, [(10.2, 10.0), (10.0, 39.8)], 3.9) == [1, 2])
    check("删面: 只有错半径面→放弃",
          _conn_face_pick([(1, 10.0, 10.0, 300.0)], [(10.0, 10.0)], 3.9) is None)
    check("删面: 距离超门控→放弃",
          _conn_face_pick([(1, 50.0, 50.0, 3.9)], [(10.0, 10.0)], 3.9) is None)
    check("护栏: 全图层但半径收窄→放行(压线板式需求)",
          not anchors_overflow(list(range(47)),
                               sanitize_std_rule({"layer": "", "r_max": 20})))
    # 以下三项依赖外部配置; nx_std_config.py 缺失时应跳过而非崩
    # (v1.29: 配置按设计是可选的, 缺失走内置兜底表, 自测不该因此 AttributeError)
    cfg = _USER_CFG
    check("BOOL_OPTS 无停用项", all(b[0] != "OFF" for b in BOOL_OPTS))
    if cfg is None:
        # 配置缺失走内置回退, 不得 AttributeError 崩溃(v1.29 声明; v1.35 补守卫)
        check("ZMODE 无绝对Z项/配置缺失回退内置",
              all(z[0] != "ABS" for z in ZMODE_OPTS)
              and [z[0] for z in ZMODE_OPTS]
              == [d[0] for d in _ZMODE_FALLBACK])
    else:
        check("ZMODE 无绝对Z项/由config表驱动(v1.32)",
              all(z[0] != "ABS" for z in ZMODE_OPTS)
              and [z[0] for z in ZMODE_OPTS] ==
              [d[0] for d in cfg.ZMODE_DEFS]
              and [z[1] for z in ZMODE_OPTS] ==
              [d[1] + "+偏移" for d in cfg.ZMODE_DEFS])
    check("_std_z 查表: CX_TOP 仍正确(CX -30~-65 → -30)",
          _std_z({"CX": (-30.0, -65.0)},
                 sanitize_std_rule({"z_mode": "CX_TOP"})) == -30.0)
    _ZMODE_DEFS.append(("JT_BOTTOM", "JT底面", "JT", "BOTTOM"))
    try:
        _ok_new = _std_z({"FLB": (-40.0, -90.0), "JT": (-30.0, -100.0)},
                         sanitize_std_rule({"z_mode": "JT_BOTTOM"}))
    finally:
        _ZMODE_DEFS.pop()          # 全局表必须还原(异常也不污染, v1.35)
    check("_std_z 查表: 动态加基准(JT底→-100)即加即用", _ok_new == -100.0)
    check("_rule_usable: 无ref不可用",
          not _rule_usable({"ref": None})
          and not _rule_usable({"ref": [1, 2]})
          and _rule_usable({"ref": [1.0, 2.0, 3.0]}))
    check("_unusable_names: 列出未配置件",
          _unusable_names({"a.prt": {"ref": [0.0, 0.0, 0.0]},
                           "b.prt": {"ref": None}}) == ["b.prt"])
    _two = [("大水口-25.prt", {"layer": "RZ", "z_mode": "FLB_BOTTOM",
                               "ref": [1.0, 2.0, 3.0]}),
            ("大水口", {"layer": "RZ", "z_mode": "FLB_BOTTOM"})]
    _hit = std_part_defaults("大水口-25.prt", table=_two)
    check("两级匹配: 精确行命中",
          _hit is not None and _hit.get("ref") == [1.0, 2.0, 3.0])
    _hit2 = std_part_defaults("大水口-18.prt", table=_two)
    check("两级匹配: 落关键词行(无ref)",
          _hit2 is not None and _hit2.get("ref") is None)
    _old = sanitize_std_rule({"bool_mode": "OFF", "z_mode": "ABS"})
    check("sanitize: 旧OFF/ABS回默认",
          _old["bool_mode"] == "PLACE" and _old["z_mode"] == "FLB_TOP")
    check("护栏常量来自配置",
          cfg is None or STD_MAX_ANCHORS == cfg.STD_MAX_ANCHORS)
    # 期刊 journal-djk.py 地面真值: 点胶口-18 起始点 (1594.78,-395.73,-570.189)
    # jrt 记忆: start/end 有记忆用记忆; 无记忆按 FLB 联动; 三参数恒默认
    jm1 = jrt_with_memory({"schema": SCHEMA_VERSION,
                           "jrt_se": [-38.0, -45.5]},
                          {"FLB": (-40.0, -90.0)})
    check("jrt_with_memory 有记忆用记忆",
          jm1["start"] == -38.0 and jm1["end"] == -45.5
          and jm1["blend_r"] == 3.9 and jm1["r_step"] == 0.1
          and jm1["r_min"] == 3.7)
    jm2 = jrt_with_memory({"schema": SCHEMA_VERSION},
                          {"FLB": (-40.0, -90.0)})
    check("jrt_with_memory 无记忆随FLB联动",
          jm2["start"] == -40.0 and jm2["end"] == -47.5)
    import inspect as _insp
    check("save_state 支持 jrt_se 字段",
          "jrt_se" in _insp.signature(save_state).parameters)
    # 配置表归用户维护(压线板已由用户自行加入), 通用默认路径用保证
    # 不在表中的名字测试
    # v1.24 连接线泛化(01.dxf 环形通道: 4 条等长 6.09 跨接线)
    _ring = [DXLine((483.5, 84.9), (483.5, 91.0)),    # 跨接线
             DXLine((483.5, 91.0), (491.5, 91.0)),    # 出线口线(8mm)
             DXLine((491.5, 91.0), (491.5, 84.9)),    # 跨接线
             DXArc((500.0, 84.9), 8.5, 0, math.pi),   # 底部过渡弧
             DXLine((508.5, 84.9), (508.5, 91.0)),
             DXLine((516.5, 91.0), (508.5, 91.0)),    # 出线口线(8mm)
             DXLine((516.5, 91.0), (516.5, 84.9)),
             DXArc((500.0, 84.9), 16.5, math.pi, 0)]  # 顶部大弧闭环
    _ring_ch = [(i, False) for i in range(len(_ring))]
    _rc = _chain_connectors(_ring_ch, _ring)
    check("连接线泛化: 环形通道4条跨接线",
          len(_rc) == 4, str(_rc))
    _om = _chain_outlet_mids(_ring_ch, _ring)
    check("出线口线中点: 2条口线(期刊删除面锚点)",
          len(_om) == 2
          and any(abs(m[0] - 487.5) < 0.01 for m in _om)
          and any(abs(m[0] - 512.5) < 0.01 for m in _om), str(_om))
    # v1.29 参考点自助配置
    check("sanitize ref: 合法3数保留",
          sanitize_std_rule({"ref": [1, 2.5, -3]})["ref"] == [1.0, 2.5, -3.0])
    check("sanitize ref: 数字字符串转float",
          sanitize_std_rule({"ref": ["1", "2.5", "-3"]})["ref"] == [1.0, 2.5, -3.0])
    check("sanitize ref: 非3长/坏值/缺失→None",
          sanitize_std_rule({"ref": [1, 2]})["ref"] is None
          and sanitize_std_rule({"ref": [1, "x", 3]})["ref"] is None
          and sanitize_std_rule({})["ref"] is None)
    _disc2 = discover_std_parts
    globals()["discover_std_parts"] = lambda: ["垫片.prt"]
    try:
        _mr = merge_std_rules({"schema": SCHEMA_VERSION,
                               "std_parts": {"垫片.prt": {
                                   "layer": "DK", "ref": [7, 8, 9]}}})
    finally:
        globals()["discover_std_parts"] = _disc2
    check("记忆往返: ref 不丢",
          _mr["垫片.prt"]["ref"] == [7.0, 8.0, 9.0])
    _rt = json.loads(json.dumps(_mr))
    _mr2 = merge_std_rules({"schema": SCHEMA_VERSION, "std_parts": _rt})
    check("json 往返: ref 不丢", _mr2["垫片.prt"]["ref"] == [7.0, 8.0, 9.0])
    # v1.26 厚度预防式起试半径
    check("齐平端起试R: 7.5厚条→3.7(用户手工值)",
          _flush_start_r(3.9, 3.7, 7.5) == 3.7)
    check("齐平端起试R: 厚条→用满blend_r",
          _flush_start_r(3.9, 3.7, 20.0) == 3.9)
    check("齐平端起试R: 不低于r_min",
          _flush_start_r(3.9, 3.7, 4.0) == 3.7)
    _nohit = std_part_defaults("未知新件XYZ.prt")
    check("表外新件→None(恢复=通用安全默认)",
          _nohit is None
          and sanitize_std_rule(_nohit)["layer"] == ""
          and sanitize_std_rule(_nohit)["bool_mode"] == "PLACE")
    sr = sanitize_std_rule({"off_x": "abc", "layer": "rz", "z_mode": "XX"})
    check("规则规范化: 坏偏移回0/坏z_mode回默认",
          sr["off_x"] == 0.0 and sr["layer"] == "RZ"
          and sr["z_mode"] == "FLB_TOP")
    check("规则规范化: CXK/CX_TOP 合法保留",
          sanitize_std_rule({"layer": "cxk", "z_mode": "cx_top",
                             "off_x": 5})["layer"] == "CXK")
    # JSON 记忆 schema 守卫(版本不符全忽略防污染; 调大 CONFIG_SCHEMA_VERSION
    # 即可清洗旧规则记忆——点胶口 z_mode/垫片 bool 脏数据一案)
    check("外部配置已加载(nx_std_config.py)", cfg is not None,
          "缺失时走内置兜底表")
    for k, v in (cfg.STD_PART_DEFAULTS if cfg is not None else []):
        rr = sanitize_std_rule(v)
        check("配置表条目合法: %s" % k,
              rr["layer"] in LAYER_CODES + ["CXK", ""]
              and rr["z_mode"] in [z for z, _t in ZMODE_OPTS]
              and rr["bool_mode"] in [b for b, _t in BOOL_OPTS]
              and rr["dir"] in [dd for dd, _t in DIR_OPTS])
    check("JRT 三参来自配置",
          cfg is None or (DEFAULT_JRT["blend_r"] == cfg.JRT_BLEND_R_DEFAULT
                          and DEFAULT_JRT["r_min"] == cfg.JRT_R_MIN_DEFAULT))
    check("配置表无重复关键词(后者永不生效)",
          cfg is None or len([k for k, _v in cfg.STD_PART_DEFAULTS])
          == len(set(k for k, _v in cfg.STD_PART_DEFAULTS)))
    _disc = discover_std_parts
    globals()["discover_std_parts"] = lambda: ["垫片.prt"]
    try:
        m_stale = merge_std_rules({"schema": SCHEMA_VERSION - 1,
                                   "std_parts": {"垫片.prt": {"layer": "LS"}}})
        m_ok = merge_std_rules({"schema": SCHEMA_VERSION,
                                "std_parts": {"垫片.prt": {"layer": "LS"}}})
    finally:
        globals()["discover_std_parts"] = _disc
    check("JSON 记忆 schema 守卫",
          m_stale["垫片.prt"]["layer"] == "DK"
          and m_ok["垫片.prt"]["layer"] == "LS")
    # 选择对话框 dlx(两段式第一段)
    sxml = build_selection_dlx(["a.prt", "b.prt"], ["b.prt"])
    try:
        ET.fromstring(sxml)
        check("选择对话框 dlx 良构", True)
    except ET.ParseError as ex:
        check("选择对话框 dlx 良构", False, str(ex))
    check("选择对话框 toggle=2 且 b 选中",
          sxml.count('class="UICOMP_toggle" hierarchy="UGS::UICOMP_group"') == 2
          and 'id="SEL1"' in sxml)

    # 8. JRT 收口连接线识别(真实 3Dtest.dxf; 期刊删面位置=连接线中点旁)
    real2 = os.path.join(script_dir(), "3Dtest.dxf")
    if os.path.isfile(real2):
        layers_r2, _ = parse_dxf(real2)
        jrt_ents = layers_r2.get("JRT") or []
        closed_r, _o = find_chains(jrt_ents)
        if len(closed_r) == 2:
            c1 = _chain_connectors(closed_r[0], jrt_ents)
            c2 = _chain_connectors(closed_r[1], jrt_ents)
            ok1 = (len(c1) == 2
                   and abs(c1[0][0] - 4615.7) < 1.5 and abs(c1[0][1] - 1366.3) < 1.5
                   and abs(c1[1][0] - 4616.2) < 1.5 and abs(c1[1][1] - 1391.3) < 1.5)
            ok2 = (len(c2) == 2
                   and abs(min(c2[0][0], c2[1][0]) - 4342.1) < 1.5
                   and abs(max(c2[0][0], c2[1][0]) - 4348.4) < 1.5)
            check("3Dtest 链1 连接线≈(4615.7,1366.3)/(4616.2,1391.3)", ok1, str(c1))
            check("3Dtest 链2 连接线≈(4342.1,1387.9)/(4348.4,1412.1)", ok2, str(c2))
    profs_dpx, opens_dp, _ = organize_loops(layers["DP"])
    check("DP 垫片嵌套", len(profs_dpx) == 1 and len(profs_dpx[0]["holes"]) == 1)
    profs_flb, _o, _c = organize_loops(layers["FLB"])
    check("FLB 双通道=2 轮廓", len(profs_flb) == 2)

    # 9. dlx 生成 + XML 良构
    xml = build_dlx(default_params())
    try:
        ET.fromstring(xml)
        check("dlx XML 良构", True)
    except ET.ParseError as ex:
        check("dlx XML 良构", False, str(ex))
    dbl = xml.count('<item Expanded="1" class="UICOMP_double"')
    check("dlx double 块数=19(图层14+JRT5)", dbl == 19, "got %d" % dbl)

    # 10. 标准件规则与锚点(纯逻辑)
    r = sanitize_std_rule({"layer": "rz", "r_min": "abc", "r_max": 5, "bool_mode": "XX"})
    check("规则规范化", r["layer"] == "RZ" and r["r_min"] == 0.0
          and r["bool_mode"] == "PLACE")
    r2 = sanitize_std_rule({"r_min": 10, "r_max": 2})
    check("半径区间自动交换", r2["r_min"] == 2.0 and r2["r_max"] == 10.0)
    check("文件名猜规则", guess_std_rule("热咀big.prt")["layer"] == "RZ"
          and guess_std_rule("screw_M8.prt")["layer"] == "LS")

    lay_c = {"RZ": [DXCircle((100, 20), 11.35), DXCircle((100, 100), 11.35),
                    DXArc((100, 20), 11.35, 0, math.pi)],
             "LS": [DXCircle((10, 10), 4.25)]}
    a1 = collect_circle_anchors(lay_c, sanitize_std_rule(
        {"layer": "RZ", "r_min": 10, "r_max": 12}))
    check("圆心锚点筛选+同心去重", len(a1) == 2, str(a1))
    a2 = collect_circle_anchors(lay_c, sanitize_std_rule({"layer": ""}))
    check("全图层锚点", len(a2) == 3, "got %d" % len(a2))
    check("_std_z 负区间", _std_z({"FLB": (-40, -85)},
                                  sanitize_std_rule({"z_mode": "FLB_TOP",
                                                     "off_z": -5})) == -45.0
          and _std_z({"FLB": (-40, -85)},
                     sanitize_std_rule({"z_mode": "FLB_BOTTOM"})) == -85.0)

    # 11. 窗口② dlx: 标准件组已在 v1.35 删除(参数页只在窗口③ build_std_dlx)
    xml2 = build_dlx(default_params(), dict(DEFAULT_JRT))
    check("窗口②无标准件组(v1.35 休眠段删除)",
          'id="grp_std"' not in xml2 and "SP0_" not in xml2
          and 'id="jrt_start"' in xml2)
    # 三段式: 窗口②无标准件组; 窗口③每件一个可收起组
    gi = _group_item("g1", "标题", _blk_label("l1", "x"), columns=2, collapsed=True)
    check("组可收起(collapsed)", 'id="Expanded" mask="0" name="Expanded" sname="Expanded" '
          'source="2" type="logical" value="False"' in gi)
    fake_rules = {"a.prt": sanitize_std_rule({"layer": "DK"}),
                  "b.prt": sanitize_std_rule({"layer": "LS"})}
    sxml = build_std_dlx(fake_rules, default_params())
    try:
        ET.fromstring(sxml)
        check("标准件参数窗口 dlx 良构", True)
    except ET.ParseError as ex:
        check("标准件参数窗口 dlx 良构", False, str(ex))
    _sxml_cxk = build_std_dlx(
        {"接线盒-24针.prt": sanitize_std_rule({"layer": "CXK",
                                               "z_mode": "CX_TOP"}),
         "垫片.prt": sanitize_std_rule({"layer": "DK"})},
        default_params())
    check("CXK件无半径框/圆心件有(v1.31)",
          "接线盒" in _sxml_cxk
          and 'value="SP0_rmin"' in _sxml_cxk
          and 'value="SP0_rmax"' in _sxml_cxk
          and 'value="SP1_rmin"' not in _sxml_cxk
          and 'value="SP1_rmax"' not in _sxml_cxk)
    check("标准件参数窗口 2 组+Z标签",
          sxml.count('id="grp_SP') == 2 and 'id="SP0_zval"' in sxml)
    check("标准件参数窗口组默认展开(v1.16)",
          'name="Expanded" sname="Expanded" '
          'source="2" type="logical" value="False"' not in sxml)
    check("全件含重置按钮(v1.19, 含无默认件)",
          'id="SP0_reset"' in sxml and 'id="SP1_reset"' in sxml)
    sxml_w = build_std_dlx({"垫片.prt": sanitize_std_rule({})}, default_params())
    check("有默认件含重置按钮(垫片)", 'id="SP0_reset"' in sxml_w
          and 'id="SP0_zval"' in sxml_w)
    g6 = guess_std_rule("点胶口-25.prt")
    check("猜测: 点胶口→RZ/FLB底(与大水口同逻辑)",
          g6["layer"] == "RZ" and g6["z_mode"] == "FLB_BOTTOM")

    # 11b. v1.35 审计修复回归断言(边界/异常/压力)
    import tempfile as _tf
    import shutil as _sh
    _td = _tf.mkdtemp(prefix="cad3d_selftest_")
    try:
        # 边界: 空 DXF / 不支持实体统计(LWPOLYLINE 不静默丢)
        _empty = os.path.join(_td, "empty.dxf")
        with io.open(_empty, "w", encoding="ascii", newline="\n") as _f:
            _f.write("0\nEOF\n")
        _el, _es = parse_dxf(_empty)
        check("空 DXF 不崩(无 ENTITIES 段)", _el == {} and _es["total"] == 0)
        _uns_dxf = os.path.join(_td, "uns.dxf")
        with io.open(_uns_dxf, "w", encoding="ascii", newline="\n") as _f:
            _f.write("\n".join(
                ["0", "SECTION", "2", "ENTITIES",
                 "0", "LWPOLYLINE", "8", "FLB", "90", "3", "70", "0",
                 "10", "0", "20", "0", "10", "10", "20", "0",
                 "10", "10", "20", "10",
                 "0", "LINE", "8", "FLB",
                 "10", "0", "20", "0", "11", "10", "21", "0",
                 "0", "LWPOLYLINE", "8", "JRT", "90", "2", "70", "1",
                 "10", "0", "20", "200", "10", "5", "20", "200",
                 "0", "ENDSEC", "0", "EOF"]))
        _ul, _us = parse_dxf(_uns_dxf)
        check("不支持实体计数(LWPOLYLINE 不静默丢)",
              _us["unsupported"].get("LWPOLYLINE") == 2
              and _us["unsupported_model"] == 1
              and _us["total"] == 1 and len(_ul.get("FLB") or []) == 1,
              str(_us))
        # 边界: 断口 0.006(<容差) 但跨量化格边界 → 邻桶搜索仍连链
        _gl = [DXLine((0, 0), (10.0, 0.0)), DXLine((9.994, 0.0), (20.0, 0.0))]
        _gc, _go = find_chains(_gl)
        check("格点边界断口仍能连链(邻桶)",
              not _gc and len(_go) == 1 and len(_go[0]) == 2)
        # 边界: T 形三叉 → 直线延续优先, 不串进垂线
        _tj = [DXLine((0, 0), (10, 0)), DXLine((10, 0), (20, 0)),
               DXLine((10, 0), (10, 10))]
        _tc, _to = find_chains(_tj)
        check("T形三叉: 直线延续优先(不串错链)",
              not _tc and len(_to) == 2 and {i for i, _r in _to[0]} == {0, 1})
        # 边界: 双重描线的重复环 → 去重, 不被误判为孔
        _dp, _do, _ = organize_loops(_sq(0, 0, 100, 100) + _sq(0, 0, 100, 100))
        check("重复描线环去重(不被误判为孔)",
              len(_dp) == 1 and not _dp[0]["holes"], "profiles=%d" % len(_dp))
        # 正确性: -Z 翻转件放置位移(ref 的 y/z 随姿态反号)
        check("-Z 放置位移(ref 随姿态旋转)",
              _place_delta((10.0, 2.0, 3.0), False, (1.0, 1.0, 1.0))
              == (-9.0, -1.0, -2.0)
              and _place_delta((10.0, 2.0, 3.0), True, (1.0, 1.0, 1.0))
              == (-9.0, 3.0, 4.0))
        # 异常: merge_params 坏类型不崩 + schema 门控 params(文档口径)
        check("merge_params 坏类型不崩",
              merge_params({"schema": SCHEMA_VERSION, "params": [1, 2]})
              == default_params()
              and merge_params({"schema": SCHEMA_VERSION, "params": "x"})
              == default_params()
              and merge_params(None) == default_params())
        _mp = merge_params({"schema": SCHEMA_VERSION,
                            "params": {"FLB": ["1.5", 2], "CX": (3, 4),
                                       "BAD": (1, 2)}})
        check("merge_params 合法值照收",
              _mp["FLB"] == (1.5, 2.0) and _mp["CX"] == (3.0, 4.0))
        check("schema 不符→params 一并回默认(文档口径)",
              merge_params({"schema": SCHEMA_VERSION - 1,
                            "params": {"FLB": (1.0, 2.0)}}) == default_params())
        check("selected 坏类型容错",
              _name_list(None) == [] and _name_list(5) == []
              and _name_list("ab") == []
              and _name_list(["a", 2]) == ["a", "2"])
        check("config 标量非法回默认不崩",
              _cfg_num("abc", 7.5) == 7.5 and _cfg_num(float("nan"), 3.0) == 3.0
              and _cfg_num("3.5", 1.0) == 3.5
              and _cfg_int(object(), 70) == 70
              and _cfg_int(float("inf"), 70) == 70)
        # 异常: 坏 JSON 记忆隔离留证 + save_state 原子写(临时目录, 猴补路径)
        _bad = os.path.join(_td, "nx_extrude_params.json")
        with io.open(_bad, "w", encoding="utf-8") as _f:
            _f.write("{oops not json")
        _saved_jp = globals()["_json_path"]
        _ok_iso = _ok_atomic = False
        globals()["_json_path"] = lambda: _bad
        try:
            _st = load_state()
            _ok_iso = (isinstance(_st, dict) and not _st and
                       [n for n in os.listdir(_td)
                        if n.startswith("nx_extrude_params.json.bad-")] != [])
        finally:
            globals()["_json_path"] = _saved_jp
        check("坏 JSON 记忆隔离留证(.bad-*)", _ok_iso)
        globals()["_json_path"] = lambda: _bad
        try:
            save_state("X:/a.dxf", {"FLB": (1.0, 2.0)},
                       selected=["a.prt"], jrt_se=(1, 2))
            _st2 = load_state()
            _ok_atomic = (_st2.get("dxf_path") == "X:/a.dxf"
                          and _st2.get("selected") == ["a.prt"]
                          and not [n for n in os.listdir(_td)
                                   if n.endswith(".tmp")])
        finally:
            globals()["_json_path"] = _saved_jp
        check("save_state 原子写+类型容错", _ok_atomic)
        # 异常: _find 对 None 不缓存(可重试)
        class _FakeTop(object):
            def __init__(self):
                self.calls = 0

            def FindBlock(self, _bid):
                self.calls += 1
                return None

        class _FakeDialog(object):
            def __init__(self):
                self.TopBlock = _FakeTop()

        class _FakeBase(_BlockDialogBase):
            def __init__(self):
                self.blocks = {}
                self.theDialog = _FakeDialog()

        _fb = _FakeBase()
        _fb._find("x")
        _fb._find("x")
        check("_find None 不缓存(可重试)", _fb.theDialog.TopBlock.calls == 2)
        # 压力: 锚点收集 4000 实体(2000 重复) <2s 且去重正确
        _big = {"RZ": [DXCircle((float(i % 100) * 10.0, float(i // 100) * 10.0), 5.0)
                       for i in range(2000)]
                + [DXCircle((float(i % 100) * 10.0, float(i // 100) * 10.0), 5.0)
                   for i in range(2000)]}
        _t0 = time.time()
        _ab = collect_circle_anchors(_big, sanitize_std_rule({"layer": "RZ"}))
        _dt = time.time() - _t0
        check("锚点去重 4000 实体 <2s 且去重正确",
              len(_ab) == 2000 and _dt < 2.0, "%.3fs" % _dt)
        # 压力: 200 个互不嵌套矩形组织 <3s
        _many = []
        for _r in range(200):
            _mx = float((_r % 20) * 30)
            _my = float((_r // 20) * 30)
            _many += _sq(_mx, _my, 20, 20)
        _t0 = time.time()
        _mp2, _mo2, _ = organize_loops(_many)
        _dt2 = time.time() - _t0
        check("organize_loops 200 环冒烟 <3s",
              len(_mp2) == 200 and _dt2 < 3.0, "%.3fs" % _dt2)
    finally:
        _sh.rmtree(_td, ignore_errors=True)

    # 12. 真实图纸(可选)
    real = dxf_path
    if not real:
        cand = os.path.join(script_dir(), "Drawing5.dxf")
        real = cand if os.path.isfile(cand) else None
    if real:
        layers_r, stats_r = parse_dxf(real)
        print("[INFO] %s: 实体 %d, 图层 %s, 参考(不建模) %s" % (
            os.path.basename(real), stats_r["total"],
            {k: len(v) for k, v in layers_r.items()}, stats_r["ref_layers"]))
    print("SELFTEST %s" % ("OK" if ok else "FAILED"))
    return ok


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
    for _note in _CFG_NOTES:
        log("【配置提示】%s" % _note)
    ok1, stats1 = run_pipeline(dxf, params, session=session, work_part=work_part,
                               log=log, std_rules=std_rules, jrt=jrt)
    ok2, stats2 = run_pipeline(dxf, params, session=session, work_part=work_part,
                               log=log, std_rules=std_rules, jrt=jrt)
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

    if _CFG_NOTES:                 # 配置/记忆加载异常: 醒目提示, 不静默回退
        NXOpen.UI.GetUI().NXMessageBox.Show(
            "CAD3D 配置提示", NXOpen.NXMessageBox.DialogType.Warning,
            "\n".join(_CFG_NOTES))

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
                               else None))
        std_rules = {f: std_rules_all[f] for f in selected}
    else:
        std_rules = {}

    # 第二段: 主参数窗口(FLB/图层/JRT; 无标准件组; OK 只收集不执行)
    dlx = write_dlx(params, jrt)
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
                f.write(build_dlx(params, jrt))
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

    # 第二页参数即刻落盘(窗口③取消也不丢; 规则仍由窗口③/执行链路保存)
    try:
        save_state(dxf2 or resolve_dxf_path(state), params2, std_rules_all,
                   selected=selected,
                   jrt_se=[float(jrt2.get("start", 0.0)),
                           float(jrt2.get("end", 0.0))])
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
                                   selected, std_rules_all=std_rules_all)
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
                         std_rules_all=std_rules_all, selected=selected or [])


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
