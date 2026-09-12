#!/usr/bin/env python3
"""Integrity checks for the Industry-Function Mapping data.

    python3 build/validate.py

Catches the mistakes a growing mapping actually makes: a use case pointing at a
sector code that was renamed, two primary functions, an ISIC class filed under
the wrong division, a documentation link to a directory that has since moved.

Exits non-zero on any error. Warnings never fail the build.
"""

# SPDX-License-Identifier: MIT

from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from model import Model  # noqa: E402

SECTOR_ID = re.compile(r"^ISIC-[A-U](-\d{2}(\d{2})?)?$")
SLUG = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
CODE_STATUS = {"verified", "provisional"}
MATURITY = {"Exploratory", "Modelled", "Live"}
MATCH_TYPES = {"exactMatch", "closeMatch", "broadMatch", "narrowMatch", "relatedMatch"}
DOC_URL = re.compile(r"^https://\S+$")

errors: list[str] = []
warnings: list[str] = []


def error(message):
    errors.append(message)


def warn(message):
    warnings.append(message)


def check_sectors(model):
    for sector_id, row in model.sectors.items():
        where = f"sectors.csv[{sector_id}]"
        if not SECTOR_ID.match(sector_id):
            error(f"{where}: id must look like ISIC-C, ISIC-C-30 or ISIC-C-3030")
        if row["code_status"] not in CODE_STATUS:
            error(f"{where}: code_status {row['code_status']!r} not in {sorted(CODE_STATUS)}")

        level, notation, broader = row["level"], row["notation"], row["broader"]
        if broader and broader not in model.sectors:
            error(f"{where}: broader {broader!r} does not exist")
            continue

        if level == "section":
            if not re.fullmatch(r"[A-U]", notation):
                error(f"{where}: a section notation must be one letter A-U, got {notation!r}")
            if broader:
                error(f"{where}: a section must not have a broader concept")
            if row["nace_rev2"] != notation:
                error(f"{where}: NACE and ISIC are identical at section level, "
                      f"expected nace_rev2={notation!r}")
        elif level == "division":
            if not re.fullmatch(r"\d{2}", notation):
                error(f"{where}: a division notation must be two digits, got {notation!r}")
            if not broader or model.sectors[broader]["level"] != "section":
                error(f"{where}: a division must sit directly under a section")
            if row["nace_rev2"] != notation:
                error(f"{where}: NACE and ISIC are identical at division level, "
                      f"expected nace_rev2={notation!r}")
        elif level == "class":
            if not re.fullmatch(r"\d{4}", notation):
                error(f"{where}: a class notation must be four digits, got {notation!r}")
            if not broader or model.sectors[broader]["level"] != "division":
                error(f"{where}: a class must sit directly under a division")
            elif not notation.startswith(model.sectors[broader]["notation"]):
                error(f"{where}: class {notation} is not inside division "
                      f"{model.sectors[broader]['notation']}")
            if row["nace_rev2"]:
                error(f"{where}: ISIC and NACE diverge below division level; "
                      f"nace_rev2 must be empty at class level")
        else:
            error(f"{where}: unknown level {level!r}")

        if model.section_of(sector_id) is None:
            error(f"{where}: does not resolve to an ISIC section (broken or cyclic broader)")


def check_functions(model):
    aligned = {a["function_id"] for a in model.alignments}
    for function_id, row in model.functions.items():
        where = f"functions.csv[{function_id}]"
        if not SLUG.match(function_id):
            error(f"{where}: id must be a lower-case slug")
        if not row["definition"].strip():
            error(f"{where}: a function without a definition cannot be mapped consistently")
        if row["broader"] and row["broader"] not in model.functions:
            error(f"{where}: broader {row['broader']!r} does not exist")
        if function_id not in aligned:
            warn(f"{where}: no alignment to CBF or APQC PCF — the function is an island")

    for cbf_id, row in model.cbf.items():
        if row["broader"] and row["broader"] not in model.cbf:
            error(f"cbf.csv[{cbf_id}]: broader {row['broader']!r} does not exist")
        if row["code_status"] not in CODE_STATUS:
            error(f"cbf.csv[{cbf_id}]: bad code_status {row['code_status']!r}")


def check_alignments(model):
    targets = {"cbf": model.cbf, "apqc-pcf": model.apqc}
    seen = set()
    for index, row in enumerate(model.alignments, start=2):
        where = f"function-alignments.csv:{index}"
        if row["function_id"] not in model.functions:
            error(f"{where}: unknown function {row['function_id']!r}")
        if row["target_scheme"] not in targets:
            error(f"{where}: unknown target_scheme {row['target_scheme']!r}")
        elif row["target_id"] not in targets[row["target_scheme"]]:
            error(f"{where}: {row['target_id']!r} is not in scheme {row['target_scheme']}")
        if row["match_type"] not in MATCH_TYPES:
            error(f"{where}: match_type {row['match_type']!r} is not a SKOS mapping relation")
        if row["status"] not in CODE_STATUS:
            error(f"{where}: bad status {row['status']!r}")
        key = (row["function_id"], row["target_scheme"], row["target_id"])
        if key in seen:
            error(f"{where}: duplicate alignment {key}")
        seen.add(key)


def check_use_cases(model):
    for uc_id, row in model.use_cases.items():
        where = f"use-cases.csv[{uc_id}]"
        if not SLUG.match(uc_id):
            error(f"{where}: id must be a lower-case slug")
        if row["maturity"] not in MATURITY:
            error(f"{where}: maturity {row['maturity']!r} not in {sorted(MATURITY)}")

        sectors = model.sectors_of.get(uc_id, [])
        if not sectors:
            error(f"{where}: no sector — a use case that sits in no sector is not a use case")
        if len(sectors) != len(set(sectors)):
            error(f"{where}: the same sector is listed twice")

        functions = [r["function_id"] for r in model.functions_of.get(uc_id, [])]
        if len(functions) != len(set(functions)):
            error(f"{where}: the same function is listed twice")
        primaries = [r for r in model.functions_of.get(uc_id, []) if r["role"] == "primary"]
        if len(primaries) != 1:
            error(f"{where}: expected exactly one primary function, found {len(primaries)}")
        for link in model.functions_of.get(uc_id, []):
            if link["role"] not in {"primary", "supporting"}:
                error(f"{where}: role {link['role']!r} must be primary or supporting")

        documented = row["documented_by"].strip()
        if documented:
            # The worked flows live in other repositories, so this checks the shape
            # of the link, not that it resolves — no network call in CI.
            if not DOC_URL.match(documented):
                error(f"{where}: documented_by must be an absolute https URL, "
                      f"got {documented!r}")
            if row["maturity"] == "Exploratory":
                warn(f"{where}: has a worked flow but is still marked Exploratory")
        elif row["maturity"] != "Exploratory":
            error(f"{where}: maturity {row['maturity']} claims a worked flow, "
                  f"but documented_by is empty")


def check_links(model):
    for index, row in enumerate(model.uc_sectors, start=2):
        where = f"use-case-sectors.csv:{index}"
        if row["use_case_id"] not in model.use_cases:
            error(f"{where}: unknown use case {row['use_case_id']!r}")
        if row["sector_id"] not in model.sectors:
            error(f"{where}: unknown sector {row['sector_id']!r}")
    for index, row in enumerate(model.uc_functions, start=2):
        where = f"use-case-functions.csv:{index}"
        if row["use_case_id"] not in model.use_cases:
            error(f"{where}: unknown use case {row['use_case_id']!r}")
        if row["function_id"] not in model.functions:
            error(f"{where}: unknown function {row['function_id']!r}")

    used_functions = {r["function_id"] for r in model.uc_functions}
    for function_id in model.functions:
        if function_id not in used_functions:
            warn(f"functions.csv[{function_id}]: not used by any use case")


def check_rdf():
    """Parse the generated graph if rdflib is installed; skip cleanly if not."""
    try:
        from rdflib import Graph
    except ImportError:
        warn("rdflib not installed — skipped parsing the generated RDF "
             "(pip install rdflib to enable)")
        return
    root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
    graphs = {}
    for name, fmt in (("ontology/ifm.ttl", "turtle"),
                      ("generated/ifm-graph.ttl", "turtle"),
                      ("generated/ifm-graph.jsonld", "json-ld")):
        path = os.path.join(root, name)
        if not os.path.exists(path):
            warn(f"{name}: missing — run build/build.py")
            continue
        try:
            graphs[name] = Graph().parse(path, format=fmt)
        except Exception as exc:  # noqa: BLE001 - report any parse failure verbatim
            error(f"{name}: does not parse as {fmt}: {exc}")
    ttl = graphs.get("generated/ifm-graph.ttl")
    jsonld = graphs.get("generated/ifm-graph.jsonld")
    if ttl is not None and jsonld is not None and not ttl.isomorphic(jsonld):
        error("generated/ifm-graph.ttl and ifm-graph.jsonld are not the same graph")


def main():
    model = Model()
    check_sectors(model)
    check_functions(model)
    check_alignments(model)
    check_use_cases(model)
    check_links(model)
    check_rdf()

    for message in warnings:
        print(f"warning: {message}")
    for message in errors:
        print(f"error: {message}", file=sys.stderr)

    counts = (f"{len(model.use_cases)} use cases, {len(model.sectors)} sectors, "
              f"{len(model.functions)} functions, {len(model.alignments)} alignments")
    if errors:
        print(f"\nFAILED: {len(errors)} error(s) in {counts}", file=sys.stderr)
        return 1
    print(f"OK: {counts}, {len(warnings)} warning(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
