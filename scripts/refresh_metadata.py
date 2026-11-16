#!/usr/bin/env python3
"""Download $metadata and rebuild structured odata/*.json catalog."""

from __future__ import annotations

import json
import os
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

from dotenv import load_dotenv
import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "odata"
EDM = "{http://schemas.microsoft.com/ado/2009/11/edm}"

TYPE_PREFIXES = [
    ("Catalog_", "Catalog"),
    ("Document_", "Document"),
    ("DocumentJournal_", "DocumentJournal"),
    ("AccumulationRegister_", "AccumulationRegister"),
    ("InformationRegister_", "InformationRegister"),
    ("AccountingRegister_", "AccountingRegister"),
    ("CalculationRegister_", "CalculationRegister"),
    ("ChartOfAccounts_", "ChartOfAccounts"),
    ("ChartOfCharacteristicTypes_", "ChartOfCharacteristicTypes"),
    ("ChartOfCalculationTypes_", "ChartOfCalculationTypes"),
    ("ExchangePlan_", "ExchangePlan"),
    ("BusinessProcess_", "BusinessProcess"),
    ("Task_", "Task"),
    ("Constant_", "Constant"),
    ("Enum_", "Enum"),
]


def classify(name: str) -> tuple[str, str, str | None]:
    for pref, kind in TYPE_PREFIXES:
        if name.startswith(pref):
            suffix = None
            rest = name[len(pref) :]
            for s in ("_RecordType", "_RowType"):
                if name.endswith(s):
                    suffix = s[1:]
                    rest = name[len(pref) : -len(s)]
                    break
            return kind, rest, suffix
    return "Other", name, None


def local(tag: str) -> str:
    return tag.split("}", 1)[-1] if "}" in tag else tag


def download_metadata() -> Path:
    load_dotenv(ROOT / ".env")
    base = os.getenv("ODATA_BASE_URL", "").rstrip("/")
    user = os.getenv("ODATA_USER", "")
    password = os.getenv("ODATA_PASSWORD", "")
    timeout = float(os.getenv("ODATA_TIMEOUT", "60"))
    url = f"{base}/$metadata"
    print(f"GET {url}")
    resp = requests.get(url, auth=(user, password), timeout=timeout)
    resp.raise_for_status()
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "metadata.xml"
    path.write_bytes(resp.content)
    print(f"saved {path} ({path.stat().st_size} bytes)")
    return path


def rebuild(meta_path: Path) -> dict:
    tree = ET.parse(meta_path)
    schema = tree.getroot().find(f".//{EDM}Schema")
    if schema is None:
        raise RuntimeError("Schema not found in metadata")

    entities = []
    complex_types = []
    enum_types = []
    associations = []
    entity_sets = []
    functions = []

    for child in schema:
        tag = local(child.tag)
        if tag == "EntityType":
            name = child.get("Name")
            keys = [p.get("Name") for p in child.findall(f"{EDM}Key/{EDM}PropertyRef")]
            props = [
                {"name": p.get("Name"), "type": p.get("Type"), "nullable": p.get("Nullable")}
                for p in child.findall(f"{EDM}Property")
            ]
            navs = [
                {
                    "name": n.get("Name"),
                    "relationship": n.get("Relationship"),
                    "fromRole": n.get("FromRole"),
                    "toRole": n.get("ToRole"),
                }
                for n in child.findall(f"{EDM}NavigationProperty")
            ]
            kind, base, suffix = classify(name)
            entities.append(
                {
                    "name": name,
                    "kind": kind,
                    "baseName": base,
                    "suffix": suffix,
                    "keys": keys,
                    "properties": props,
                    "navigation": navs,
                    "propertyCount": len(props),
                }
            )
        elif tag == "ComplexType":
            props = [
                {"name": p.get("Name"), "type": p.get("Type"), "nullable": p.get("Nullable")}
                for p in child.findall(f"{EDM}Property")
            ]
            complex_types.append({"name": child.get("Name"), "properties": props, "propertyCount": len(props)})
        elif tag == "EnumType":
            members = [{"name": m.get("Name"), "value": m.get("Value")} for m in child.findall(f"{EDM}Member")]
            enum_types.append({"name": child.get("Name"), "members": members})
        elif tag == "Association":
            ends = [
                {"type": e.get("Type"), "role": e.get("Role"), "multiplicity": e.get("Multiplicity")}
                for e in child.findall(f"{EDM}End")
            ]
            associations.append({"name": child.get("Name"), "ends": ends})
        elif tag == "EntityContainer":
            for es in child.findall(f"{EDM}EntitySet"):
                entity_sets.append({"name": es.get("Name"), "entityType": es.get("EntityType")})
            for f in child.findall(f"{EDM}FunctionImport"):
                functions.append(
                    {
                        "name": f.get("Name"),
                        "returnType": f.get("ReturnType"),
                        "entitySet": f.get("EntitySet"),
                        "httpMethod": f.get(
                            "{http://schemas.microsoft.com/ado/2007/08/dataservices/metadata}HttpMethod"
                        ),
                    }
                )

    by_kind_sets: dict[str, list] = defaultdict(list)
    for es in entity_sets:
        kind, base, suffix = classify(es["name"])
        by_kind_sets[kind].append(
            {"name": es["name"], "baseName": base, "suffix": suffix, "entityType": es["entityType"]}
        )

    summary = {
        "source": os.getenv("ODATA_BASE_URL", "") + "/$metadata",
        "serviceRoot": os.getenv("ODATA_BASE_URL", "") + "/",
        "namespace": schema.get("Namespace"),
        "counts": {
            "entityTypes": len(entities),
            "complexTypes": len(complex_types),
            "enumTypes": len(enum_types),
            "associations": len(associations),
            "entitySets": len(entity_sets),
            "functionImports": len(functions),
        },
        "entitySetsByKind": {
            k: len(v) for k, v in sorted(by_kind_sets.items(), key=lambda x: -len(x[1]))
        },
    }

    (OUT / "entities").mkdir(parents=True, exist_ok=True)
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    catalog = []
    for kind in sorted(by_kind_sets.keys()):
        groups: dict[str, list] = defaultdict(list)
        for it in by_kind_sets[kind]:
            groups[it["baseName"]].append(it)
        for base, variants in sorted(groups.items()):
            main_name = next((v["name"] for v in variants if not v["suffix"]), variants[0]["name"])
            main_ent = next((e for e in entities if e["name"] == main_name), None)
            catalog.append(
                {
                    "kind": kind,
                    "name": base,
                    "collections": [v["name"] for v in variants],
                    "keys": main_ent["keys"] if main_ent else [],
                    "propertyCount": main_ent["propertyCount"] if main_ent else 0,
                    "properties": [
                        {"name": p["name"], "type": p["type"]} for p in (main_ent["properties"] if main_ent else [])
                    ],
                    "navigation": [n["name"] for n in (main_ent["navigation"] if main_ent else [])],
                }
            )

    (OUT / "catalog.json").write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")

    for kind, items in by_kind_sets.items():
        bases = sorted({i["baseName"] for i in items})
        kind_entities = []
        for base in bases:
            variants = [i for i in items if i["baseName"] == base]
            main_name = next((v["name"] for v in variants if not v["suffix"]), variants[0]["name"])
            ent = next((e for e in entities if e["name"] == main_name), None)
            kind_entities.append(
                {
                    "name": base,
                    "collections": [v["name"] for v in variants],
                    "keys": ent["keys"] if ent else [],
                    "properties": ent["properties"] if ent else [],
                    "navigation": ent["navigation"] if ent else [],
                }
            )
        (OUT / "entities" / f"{kind}.json").write_text(
            json.dumps(kind_entities, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    (OUT / "enums.json").write_text(
        json.dumps(
            [
                {"name": e["name"], "memberCount": len(e["members"]), "members": [m["name"] for m in e["members"]]}
                for e in enum_types
            ],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (OUT / "functions.json").write_text(json.dumps(functions, ensure_ascii=False, indent=2), encoding="utf-8")
    index = [
        {
            "name": e["name"],
            "kind": e["kind"],
            "baseName": e["baseName"],
            "suffix": e["suffix"],
            "keys": e["keys"],
            "propertyCount": e["propertyCount"],
        }
        for e in entities
    ]
    (OUT / "entity_types_index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def main() -> int:
    path = download_metadata()
    summary = rebuild(path)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
