# -*- coding: utf-8 -*-
"""cad3d.modeling —— NXOpen 3D 建模、装配、布尔与清理组件包。"""

from cad3d.modeling.display import _refresh_display
from cad3d.modeling.extrude import (
    _add_to_section_compat,
    _sc_rule_options,
    build_layer,
    create_curves,
    extrude_curves,
    modeling_ents,
    work_part_rules,
)
from cad3d.modeling.jrt import (
    _body_face_rows,
    _body_volume,
    _delete_faces,
    _delete_faces_safe,
    _edge_blend_end,
    _edge_blend_end_retry,
    _find_flat_face,
    _pick_conn_faces,
    _set_display,
    _uf_face_data,
    build_jrt,
)
from cad3d.modeling.nx_compat import (
    MARK_ATTR,
    _bodies_of,
    _is_marked,
    _iter,
    _mark_curve,
    _matrix3x3,
    _set_expr,
)
from cad3d.modeling.purge import _CREATED_FEATURES, ensure_categories, nx_purge
from cad3d.modeling.std_rules import (
    _rule_usable,
    _std_z,
    _unusable_names,
    anchors_overflow,
    discover_std_parts,
    guess_std_rule,
    merge_std_rules,
    sanitize_std_rule,
    std_part_defaults,
)
from cad3d.modeling.stdparts import (
    _bool_feature,
    _bool_one,
    _pick_target,
    _place_delta,
    _promote_body,
    _remove_parameters,
    _usable_parts,
    place_std_parts,
)
