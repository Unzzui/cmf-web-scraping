#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Convierte un JSON raíz con:
{
  "version": 1,
  "empresas": [
    {
      "empresa": {...},
      "lang": "es",
      "roles": [
        {"id": "...", "titulo": "...", "lineas": ["...", ...]},
        ...
      ]
    }
  ]
}

en el mismo objeto pero añadiendo role["tree"] con la estructura jerárquica.
"""

import json
import re
import sys
from copy import deepcopy

SINOPSIS_TOKEN = "[sinopsis]"

# grupos especiales que deben colgar del macro-bloque
# grupos especiales que deben colgar del macro-bloque
BANK_GROUP_PATTERNS = [
    r"^Negocios no bancarios \[sinopsis\]$",
    r"^Servicios bancarios \[sinopsis\]$",
    r"^Servicios Bancarios \[sinopsis\]$",
    r"^Activos Bancarios \[sinopsis\]$",
    r"^Pasivos Servicios Bancarios \[sinopsis\]$",
]
BANK_GROUP_RE = re.compile("|".join(BANK_GROUP_PATTERNS), flags=re.IGNORECASE)


# macro-bloques que reinician nivel
MACRO_HEADERS = [
    r"^Activos \[sinopsis\]$",
    r"^Patrimonio y pasivos \[sinopsis\]$",
    r"^Pasivos \[sinopsis\]$",
    r"^Flujos de efectivo procedentes de \(utilizados en\) actividades de operación \[sinopsis\]$",
    r"^Flujos de efectivo procedentes de \(utilizados en\) actividades de inversión \[sinopsis\]$",
    r"^Flujos de efectivo procedentes de \(utilizados en\) actividades de financiación \[sinopsis\]$",
    r"^Ganancia \(pérdida\) \[sinopsis\]$",
    # ❌ REMOVED: "Servicios bancarios [sinopsis]" NO debe ser macro-header 
    # Debe ser subcategoría que cuelga de las categorías principales de flujo de efectivo
]
MACRO_RE = re.compile("|".join(MACRO_HEADERS), flags=re.IGNORECASE)


def is_category(label: str) -> bool:
    return SINOPSIS_TOKEN in label


def make_node(label: str, kind: str):
    node = {"label": label, "kind": kind}
    if kind == "category":
        node["children"] = []
    return node


def attach_child(parent, child):
    parent.setdefault("children", []).append(child)


def build_tree_from_lines(lines):
    root = {"label": "__root__", "kind": "category", "children": []}
    stack = [root]

    def find_last_macro():
        for n in reversed(stack):
            if n is root:
                continue
            if MACRO_RE.match(n["label"] or ""):
                return n
        return root

    for raw in lines:
        label = raw.strip()
        if not label:
            continue

        if is_category(label):
            node = make_node(label, "category")
            if MACRO_RE.match(label):
                attach_child(root, node)
                stack = [root, node]
            elif BANK_GROUP_RE.match(label):
                macro_parent = find_last_macro()
                attach_child(macro_parent, node)
                stack = stack[: stack.index(macro_parent) + 1] + [node]
            else:
                attach_child(stack[-1], node)
                stack.append(node)
        else:
            node = make_node(label, "account")
            attach_child(stack[-1], node)

    return root["children"]


def transform(data):
    out = deepcopy(data)
    for empresa in out.get("empresas", []):
        for role in empresa.get("roles", []):
            role["tree"] = build_tree_from_lines(role.get("lineas", []))
    return out


def main():
    if len(sys.argv) < 3:
        print("Uso: python transformar_estructura.py input.json output.json")
        sys.exit(1)

    inp, outp = sys.argv[1], sys.argv[2]
    with open(inp, "r", encoding="utf-8") as f:
        data = json.load(f)

    result = transform(data)

    with open(outp, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"Estructura guardada en {outp}")


if __name__ == "__main__":
    main()
