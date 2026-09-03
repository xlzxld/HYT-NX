# -*- coding: utf-8 -*-
"""cad3d.modeling —— NXOpen 3D 建模、装配、布尔与清理组件包。"""

from cad3d.modeling.nx_compat import (
    MARK_ATTR, _set_expr, _mark_curve, _is_marked, _iter, _bodies_of,
    _matrix3x3
)
from cad3d.modeling.purge import (
    _CREATED_FEATURES, nx_purge, clean_previous, ensure_categories
)
from cad3d.modeling.std_rules import (
    _std_z, std_part_defaults, guess_std_rule, sanitize_std_rule,
    _rule_usable, _unusable_names, discover_std_parts, merge_std_rules,
    anchors_overflow
)
from cad3d.modeling.extrude import (
    create_curves, _create_curves, work_part_rules, _add_to_section_compat,
    _sc_rule_options, extrude_curves, modeling_ents, build_layer
)
from cad3d.modeling.stdparts import (
    _place_delta, _pick_target, _promote_body, _bool_one, _bool_feature,
    _remove_parameters, _usable_parts, place_std_parts
)
from cad3d.modeling.jrt import (
    _uf_face_data, _find_flat_face, _edge_blend_end, _body_face_rows,
    _body_volume, _edge_blend_end_retry, _delete_faces, _delete_faces_safe,
    _pick_conn_faces, _set_display, build_jrt
)
from cad3d.modeling.display import _refresh_display
