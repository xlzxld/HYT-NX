# -*- coding: utf-8 -*-
"""从 NX 官方样例 .dlx 中提取各块类型的完整 XML 模板（pretty 打印）。"""
import sys, io, xml.etree.ElementTree as ET

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

SRC = r"C:\Program Files\Siemens\NX2312\DESIGN_TOOLS\checkmate\examples\NXOpenCheckerExamples\Python\CheckDeepHoles\CheckDeepHoles_Customization.dlx"

tree = ET.parse(SRC)
root = tree.getroot()

seen = {}


def dump(elem, indent, maxdepth=99):
    pad = "  " * indent
    attrs = " ".join(f'{k}="{v}"' for k, v in elem.attrib.items())
    has_children = len(elem) > 0
    if not has_children:
        print(f"{pad}<{elem.tag} {attrs}/>")
        return
    print(f"{pad}<{elem.tag} {attrs}>")
    if indent < maxdepth:
        for c in elem:
            dump(c, indent + 1, maxdepth=maxdepth)
    print(f"{pad}</{elem.tag}>")


def walk(elem, path):
    for child in elem:
        tag = child.tag
        typ = child.get("type", "")
        cls = child.get("class", "")
        if tag == "Property" and typ == "uicomp":
            key = cls
            if key not in seen:
                seen[key] = True
                print("=" * 100)
                print(f"[BLOCK class={cls!r} presentation={child.get('presentation','')!r} path={'/'.join(path)}]")
                dump(child, 0)
        if tag in ("PropertyList", "Property", "item", "Dialog"):
            walk(child, path + [f"{tag}:{child.get('id','')}/{cls}/{typ}"])


walk(root, ["Dialog"])
print("#" * 100)
print("classes seen:", sorted(seen))
