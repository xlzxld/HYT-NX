# -*- coding: utf-8 -*-
"""cad3d.core —— 核心基础组件包。"""

from cad3d.core.paths import (
    ROOT_DIR, script_dir, _logs_dir, _fresh_dlx_path, _temp_dlx_path,
    stdparts_dir, _json_path, resolve_dxf_path
)
from cad3d.core.config import (
    _CFG_NOTES, _note, _cfg_num, _import_module_from_path,
    _load_user_config, _USER_CFG, SCHEMA_VERSION, _cfg, _cfg_int,
    _JRT_BLEND_R, _JRT_R_STEP, _JRT_R_MIN
)
from cad3d.core.constants import (
    SCRIPT_VERSION, FEATURE_PREFIX, COMP_PREFIX, LOOP_TOL, CHAIN_TOL,
    _LAYER_DEFS, _NX_LAYER_START, _LAYER_DISTS, LAYER_TABLE, LAYER_CODES,
    REF_LAYER_TABLE, DYNAMIC_START, MANAGED_MIN, MANAGED_MAX, assign_layers,
    TARGET_CODE, DIALOG_GROUPS, _LINK_OFFSETS_RAW, _LINK_OFFSETS, LINK_RULES,
    JRT_FROM_TOP, _JT_LINK_FALLBACK, JT_LINK_MODES, JT_LINK_DEFAULT,
    JT_LINK_OPTS, _CX_LINK_END_OFF, STDPARTS_DIRNAME, DEFAULT_STD_RULE,
    DEFAULT_JRT, _ZMODE_FALLBACK, _ZMODE_DEFS, ZMODE_OPTS, BOOL_OPTS,
    DIR_OPTS, LAYER_SEL_OPTS, JRT_FIELDS, STD_MAX_ANCHORS
)
from cad3d.core.logging import _fmt_num, Log
from cad3d.core.state import (
    _jt_link_values, jt_mode_with_memory, _cx_link_values, derive_linked,
    jrt_with_memory, default_params, load_state, _name_list, save_state,
    merge_params, merge_jrt
)
