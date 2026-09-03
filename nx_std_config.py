# -*- coding: utf-8 -*-
"""
nx_std_config.py —— CAD3D 全局工程参数与标准件规则配置文件
=============================================================================
适用环境：Siemens NX 10 / NX 12 / NX 2312 及以上版本（兼容 Python 3.3 ~ 3.12+）
最后更新：2026-09-03 (v2.0 定版)

【配置文件概述】
  本脚本集中管理 CAD3D 分层拉伸系统的全部出厂默认配置与工程规则。
  所有业务参数、图层定义、尺寸联动、标准件装配与系统环境均在此声明。
  用户修改本文件中的任意数值并保存后，重新在 NX 中启动日记即可立即生效，
  无需改动任何核心代码。

【配置分类索引】
  1. 架构模式与记忆门控 (CONFIG_SCHEMA_VERSION)
  2. 标准件装配规则表 (STD_PART_DEFAULTS, DEFAULT_STD_RULE, ZMODE_DEFS)
  3. 分层建模与图层定义 (LAYER_DEFS, TARGET_CODE, LAYER_START_DEFAULTS)
  4. 尺寸联动推导规则 (LINK_OFFSETS, JT_LINK_MODES, CX_LINK_END_OFFSET, JRT_INTRUSION_DEFAULT)
  5. JRT 加热条工艺与配色 (JRT_*)
  6. NX 运行环境与命名空间 (NX_LAYER_*, FEATURE_PREFIX, COMP_PREFIX, DIALOG_GROUPS)
  7. 几何算法容差与系统路径 (LOOP_TOL, CHAIN_TOL, STD_MAX_ANCHORS, 目录路径)
=============================================================================
"""

# =============================================================================
# 1. 架构模式与记忆门控
# =============================================================================
# 记忆文件 (nx_extrude_params.json) 的数据结构版本号。
# 作用：记忆文件中存有相同的版本标记。当本数字被调大时，系统判定历史记忆已过期，
#       自动忽略旧记忆中的所有参数，彻底重置并恢复为本配置文件的出厂默认值。
# 应用场景：当用户在界面中将参数调乱希望一键重置出厂状态时，将此值加 1 即可。
CONFIG_SCHEMA_VERSION = 4


# =============================================================================
# 2. 标准件装配规则表
# =============================================================================
# 标准件规则默认回退字典（当某标准件未指定某项参数时采用的安全默认值）
DEFAULT_STD_RULE = {
    "layer": "",              # 默认不限制图层（全图层匹配）
    "r_min": 0.0,             # 搜索半径下限 (mm)
    "r_max": 9999.0,          # 搜索半径上限 (mm)
    "z_mode": "FLB_TOP",      # 默认基准面：分流板顶面
    "bool_mode": "PLACE",     # 默认布尔方式：仅放置独立体
    "dir": "+Z",              # 默认装配朝向：+Z 正向插入
    "off_x": 0.0,             # X 坐标微调偏移 (mm)
    "off_y": 0.0,             # Y 坐标微调偏移 (mm)
    "off_z": 0.0,             # Z 坐标微调偏移 (mm)
    "ref": None,              # 标准件基准原点（关键词行不带 ref，需在精确文件名行提供归零原点）
}

# Z 基准模式定义表：定义界面下拉框中的 "z_mode" 基准面选项。
# 每行格式：(模式代码 key, 界面显示中文名, 参考图层代码, 取大值TOP还是取小值BOTTOM)
# 用户追加一行即可新增一种基准（如 JT 顶面），高度计算公式：Z = 参考图层极值 + off_z。
ZMODE_DEFS = [
    ("FLB_TOP", "FLB顶面", "FLB", "TOP"),
    ("FLB_BOTTOM", "FLB底面", "FLB", "BOTTOM"),
    ("CX_TOP", "CX顶值", "CX", "TOP"),
]

# 标准件规则默认值表 (STD_PART_DEFAULTS)
# 匹配机制：两级优先匹配（自上而下匹配第一条命中的规则生效）
#   1. 精确文件名行：key 包含完整文件名（如 "大水口-18.prt"），优先级最高；
#   2. 关键词行：key 为零件族通用字样（如 "大水口"、"螺丝"），用于定义同族通用默认；
# 字段说明：
#   - layer: 依据 DXF 图纸中哪个图层的图形定位（圆心或定位线中点）
#   - r_min / r_max: 针对圆心定位层，限定被捕捉圆的半径范围 (mm)
#   - z_mode: 装配高度基准面（需在 ZMODE_DEFS 中定义）
#   - bool_mode: "PLACE"(仅放置) / "PLACE_SUBTRACT"(放置并减去型腔) / "SUBTRACT"(仅切槽) / "UNITE"(合并)
#   - dir: "+Z"(正向插入) / "-Z"(翻转180度插入)
#   - off_x, off_y, off_z: 相对锚点的三维位移量 (mm)
#   - ref: 标准件几何插入参考原点，已归零零件恒为 [0.0, 0.0, 0.0]
STD_PART_DEFAULTS = [
    # ─── 精确零件行（已全部通过 nx_zero_ref.py 归零） ──────────────────────
    ("大水口-18.prt", {"layer": "RZ", "r_min": 0.0, "r_max": 15.0, "z_mode": "FLB_BOTTOM", "ref": [0.0, 0.0, 0.0]}),
    ("大水口-25.prt", {"layer": "RZ", "r_min": 0.0, "r_max": 15.0, "z_mode": "FLB_BOTTOM", "ref": [0.0, 0.0, 0.0]}),
    ("大水口-35.prt", {"layer": "RZ", "r_min": 0.0, "r_max": 15.0, "z_mode": "FLB_BOTTOM", "ref": [0.0, 0.0, 0.0]}),
    ("点胶口-18.prt", {"layer": "RZ", "r_min": 0.0, "r_max": 15.0, "z_mode": "FLB_BOTTOM", "ref": [0.0, 0.0, 0.0]}),
    ("点胶口-25.prt", {"layer": "RZ", "r_min": 0.0, "r_max": 15.0, "z_mode": "FLB_BOTTOM", "ref": [0.0, 0.0, 0.0]}),
    ("螺丝-45.prt",   {"layer": "LS", "r_min": 0.0, "r_max": 5.0, "z_mode": "FLB_TOP", "bool_mode": "PLACE_SUBTRACT", "ref": [0.0, 0.0, 0.0]}),
    ("螺丝-50.prt",   {"layer": "LS", "r_min": 0.0, "r_max": 5.0, "z_mode": "FLB_TOP", "bool_mode": "PLACE_SUBTRACT", "ref": [0.0, 0.0, 0.0]}),
    ("主进胶与中心定位垫片-30.prt", {"layer": "DP", "r_min": 0.0, "r_max": 8.0, "z_mode": "FLB_BOTTOM", "bool_mode": "PLACE_SUBTRACT", "ref": [0.0, 0.0, 0.0]}),
    ("主进胶与中心定位垫片-35.prt", {"layer": "DP", "r_min": 0.0, "r_max": 8.0, "z_mode": "FLB_BOTTOM", "bool_mode": "PLACE_SUBTRACT", "ref": [0.0, 0.0, 0.0]}),
    ("垫片.prt",       {"layer": "DK", "r_min": 0.0, "r_max": 5.0, "z_mode": "FLB_TOP", "bool_mode": "PLACE_SUBTRACT", "ref": [0.0, 0.0, 0.0]}),
    ("接线盒-16针.prt", {"layer": "CXK", "z_mode": "CX_TOP", "ref": [0.0, 0.0, 0.0]}),
    ("接线盒-24针.prt", {"layer": "CXK", "z_mode": "CX_TOP", "ref": [0.0, 0.0, 0.0]}),
    ("接线盒-48针.prt", {"layer": "CXK", "z_mode": "CX_TOP", "ref": [0.0, 0.0, 0.0]}),
    ("压线板.prt",     {"layer": "CXK", "z_mode": "CX_TOP", "ref": [0.0, 0.0, 0.0]}),

    # ─── 零件族关键词通用规则行 ──────────────────────────────────────────
    ("主进胶", {"layer": "DP", "r_min": 0.0, "r_max": 8.0, "z_mode": "FLB_BOTTOM", "bool_mode": "PLACE_SUBTRACT"}),
    ("大水口", {"layer": "RZ", "r_min": 0.0, "r_max": 15.0, "z_mode": "FLB_BOTTOM"}),
    ("点胶口", {"layer": "RZ", "r_min": 0.0, "r_max": 15.0, "z_mode": "FLB_BOTTOM"}),
    ("热咀",   {"layer": "RZ", "r_min": 0.0, "r_max": 15.0, "z_mode": "FLB_BOTTOM"}),
    ("nozzle", {"layer": "RZ", "r_min": 0.0, "r_max": 15.0, "z_mode": "FLB_BOTTOM"}),
    ("螺丝",   {"layer": "LS", "r_min": 0.0, "r_max": 5.0, "z_mode": "FLB_TOP", "bool_mode": "PLACE_SUBTRACT"}),
    ("screw",  {"layer": "LS", "r_min": 0.0, "r_max": 5.0, "z_mode": "FLB_TOP", "bool_mode": "PLACE_SUBTRACT"}),
    ("ls-",    {"layer": "LS", "r_min": 0.0, "r_max": 5.0, "z_mode": "FLB_TOP", "bool_mode": "PLACE_SUBTRACT"}),
    ("接线盒", {"layer": "CXK", "z_mode": "CX_TOP"}),
    ("垫片",   {"layer": "DK", "r_min": 0.0, "r_max": 5.0, "z_mode": "FLB_TOP", "bool_mode": "PLACE_SUBTRACT"}),
    ("washer", {"layer": "DK", "r_min": 0.0, "r_max": 5.0, "z_mode": "FLB_TOP", "bool_mode": "PLACE_SUBTRACT"}),
    ("压线板", {"layer": "CXK", "z_mode": "CX_TOP"}),
]


# =============================================================================
# 3. 分层建模与图层定义
# =============================================================================
# 布尔运算目标基准图层代码（所有减去层将从此图层生成的实体上减去型腔）
TARGET_CODE = "FLB"

# 分层图层定义表：定义全部核心建模图层。
# 每项格式：(图层代码, 中文说明, 布尔角色 role)
#   role 可选：
#     - "target"   : 主基准体（分流板实体，各封闭轮廓独立成体）
#     - "none"     : 普通独立实体（不参与布尔减，如假体、出线槽）
#     - "subtract" : 布尔减去层（拉伸后自动从所属分流板实体中精准布尔减去）
LAYER_DEFS = [
    ("FLB", "分流板", "target"),
    ("JT",  "假体",   "none"),
    ("LS",  "螺丝孔", "subtract"),
    ("RZ",  "热咀孔", "subtract"),
    ("DK",  "点孔",   "subtract"),
    ("DP",  "垫片",   "subtract"),
    ("CX",  "出线槽", "none"),
]

# 各图层默认拉伸起止距离 (mm)：[起始绝对高度, 结束绝对高度]
# 当无记忆或全新运行且不带记忆文件时，窗口②将采用此初始默认值。
LAYER_START_DEFAULTS = {
    "FLB": (-40.0, -85.0),
    "JT":  (-30.0, -100.0),
    "LS":  (-40.0, -85.0),
    "RZ":  (-72.0, -85.0),
    "DK":  (-40.0, -43.0),
    "DP":  (-78.2977, -85.0),
    "CX":  (-30.0, -65.0),
}


# =============================================================================
# 4. 尺寸联动推导规则
# =============================================================================
# 孔系与特征相对 FLB 分流板的联动偏移量 (mm)
# 当用户在窗口②中调整 FLB 厚度时，以下图层自动按公式跟随更新：
#   - RZ (热咀孔) : (FLB底面 + 此值, FLB底面) —— 热咀沉头从底面向上突出的高度
#   - DK (点孔)   : (FLB顶面, FLB顶面 − 此值) —— 点孔/销孔自顶面向下的加工深度
#   - DP (垫片层) : (FLB底面 + 此值, FLB底面) —— 垫片沉头台阶厚度（实测定位件）
LINK_OFFSETS = {
    "RZ": 13.0,
    "DK": 3.0,
    "DP": 6.7023,
}

# JT 假体联动双模式配置字典：{模式名称: (起始偏移, 结束偏移)}
#   公式：JT起始 = FLB顶面 + 起始偏移；JT结束 = FLB底面 + 结束偏移
#   普通模式：起点 +10.0 / 终点 -15.0（例如 FLB -40/-85 → JT -30/-100）
#   针阀模式：起点 +15.0 / 终点 -15.0（例如 FLB -40/-85 → JT -25/-100）
JT_LINK_MODES = {
    "普通模式": (10.0, -15.0),
    "针阀模式": (15.0, -15.0),
}
JT_LINK_DEFAULT = "普通模式"

# CX 出线槽固定槽深联动偏移 (mm)
# 公式：CX起始恒等于 JT起始；CX结束 = CX起始 − CX_LINK_END_OFFSET（槽深固定 35mm）
# 保护机制：CX 槽深固定随自身顶面走，不会因假体 JT 结束的漂移而击穿底板。
CX_LINK_END_OFFSET = 35.0

# 加热条嵌入基准板内的默认深度 (mm)
# 联动公式：JRT 起始 = FLB 顶面，JRT 结束 = FLB 顶面 − JRT_INTRUSION_DEFAULT
JRT_INTRUSION_DEFAULT = 7.5


# =============================================================================
# 5. JRT 加热条工艺与配色参数
# =============================================================================
# 倒圆几何参数（出厂默认，不存盘记忆，每次重开恒以此为准）
JRT_BLEND_R_DEFAULT = 3.9     # 加热条嵌入端倒圆起始半径 (mm)
JRT_R_STEP_DEFAULT  = 0.1     # 异形检测不过时的降级步长 (mm)
JRT_R_MIN_DEFAULT   = 3.7     # 倒圆允许降级的下限半径 (mm)

# JRT 工艺特征与显示渲染参数
JRT_OFFSET       = 5.0        # 加热条实体壁外偏置扩张量 (mm)
JRT_DRAFT        = 2.0        # 加热条拔模斜度角度 (度)
JRT_COLOR_STRIP  = 186        # 加热条实体着色 NX 色号（亮色）
JRT_COLOR_MODEL  = 78         # 分流板等模型着色 NX 色号
JRT_TRANSLUCENCY = 50         # 加热条模型透明度（0 为不透明，100 为全透）


# =============================================================================
# 6. NX 运行环境、图层号与命名空间
# =============================================================================
# NX 图层区间分配（默认分配在 101 ~ 170 高位图层，低位 1~100 彻底留给用户自绘图形；内置冲突智能避让机制）
NX_LAYER_START         = 101  # 建模图层起始层号（FLB=101, JT=102, LS=103, RZ=104, DK=105, DP=106, CX=107）
NX_LAYER_JRT           = 118  # JRT 参考线固定放入的 NX 图层号
NX_LAYER_DYNAMIC_START = 119  # 其余 DXF 图层（0、LD等）动态分配起始图层号
NX_LAYER_MAX           = 170  # 脚本管理图层上限

# 建模特征树与装配命名空间前缀（用于清理与历史追踪）
FEATURE_PREFIX = "CAD3D_"     # 自动化生成的特征名前缀
COMP_PREFIX    = "CAD3D_C_"   # 标准件装配组件实例名前缀

# 窗口② 主参数对话框分组逻辑定义：[(组ID, 组标题, [包含图层代码...])]
DIALOG_GROUPS = [
    ("grp_flb",   "FLB 分流板（基准体；改动两项后 LS/RZ/DK/DP/JRT 自动联动）", ["FLB"]),
    ("grp_plain", "普通拉伸图层（JT 随 FLB 联动；起始=结束=0 则跳过）", ["JT", "CX"]),
    ("grp_sub",   "拉伸并从 FLB 减去（随 FLB 联动，可单独改）", ["LS", "RZ", "DK", "DP"]),
]


# =============================================================================
# 7. 几何算法容差、安全护栏与系统路径
# =============================================================================
# 算法容差
LOOP_TOL  = 0.01              # 2D 轮廓端点连接闭合容差 (mm)
CHAIN_TOL = 0.01              # NX Section 链接曲线容差 (mm)

# 防卡死安全护栏：单件最大允许放置的锚点数上限。
# 保护机制：若某标准件图层误配为全部图层且半径全开，图元过多时直接阻断跳过，防止卡死 NX。
STD_MAX_ANCHORS = 200

# 文件与目录路径名称配置（相对项目根目录）
STDPARTS_DIRNAME = "stdparts"                 # 标准件 .prt 存放库目录
LOGS_DIRNAME     = "logs"                     # 动态 .dlx 与调试日志生成目录
PARAMS_FILENAME  = "nx_extrude_params.json"   # 运行时记忆持久化文件名

# AutoCAD 转换引擎路径（可选；用于自动将 .dwg 图纸后台静默转换为 .dxf 建模）
# 默认 None 表示系统自动探测（自动查找注册表及高低版本 AutoCAD 路径）
# 若您的电脑将 AutoCAD 安装在自定义特殊目录，可在此直接指定路径，例如：
# ACAD_CONSOLE_PATH = r"C:\Program Files\Autodesk\AutoCAD 2024\accoreconsole.exe"
ACAD_CONSOLE_PATH = None
