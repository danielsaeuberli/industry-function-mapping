"""Load the Industry-Function Mapping CSVs into a plain-Python model.

No third-party dependencies on purpose: the CSVs are the source of truth and
anyone with a Python 3 interpreter must be able to rebuild the graph.
"""

# SPDX-License-Identifier: MIT

from __future__ import annotations

import csv
import os

# The namespace every concept is minted under. Change this one constant (and
# rebuild) to move the vocabulary to another domain — nothing else hard-codes it.
# It matches the GitHub Pages URL of this repository, so the IRIs resolve to the
# generated matrix once Pages is enabled.
BASE = "https://danielsaeuberli.github.io/industry-function-mapping/"
ID_BASE = BASE + "id/"
ONT = BASE + "ontology#"

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
GENERATED_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "generated")

SCHEMES = {
    "isic-rev4": {
        "title": "ISIC Rev. 4 (sectors used by this repository)",
        "description": "Local SKOS rendering of the International Standard Industrial "
                       "Classification of All Economic Activities, Revision 4. All 21 "
                       "sections, plus the divisions and classes the mapped use cases "
                       "actually reach.",
        "source": "https://unstats.un.org/unsd/classifications/Econ/isic",
    },
    "cbf": {
        "title": "Classification of Business Functions (categories)",
        "description": "Business function categories following the UNECE/Eurostat "
                       "Classification of Business Functions. Labels are seeded here and "
                       "carry codeStatus 'provisional' until checked against the official "
                       "publication; no notations are invented.",
        "source": "https://unece.org/trade/statistics",
    },
    "apqc-pcf": {
        "title": "APQC Process Classification Framework (referenced categories)",
        "description": "Only the cross-industry PCF categories an alignment actually "
                       "references. The framework itself is published by APQC and is not "
                       "redistributed here.",
        "source": "https://www.apqc.org/process-frameworks",
    },
    "ifm-functions": {
        "title": "IFM operational business functions",
        "description": "The function vocabulary this repository actually maps use cases "
                       "onto. Deliberately its own scheme rather than a fork of CBF or "
                       "APQC PCF: the alignment to those is recorded as SKOS mapping "
                       "relations, so the external classifications can be swapped or "
                       "corrected without touching any use case.",
        "source": BASE,
    },
}


def _read(name):
    with open(os.path.join(DATA_DIR, name), newline="", encoding="utf-8") as fh:
        return [dict(row) for row in csv.DictReader(fh)]


class Model:
    def __init__(self):
        self.sectors = {r["id"]: r for r in _read("sectors.csv")}
        self.cbf = {r["id"]: r for r in _read("cbf.csv")}
        self.apqc = {r["id"]: r for r in _read("apqc-pcf.csv")}
        self.functions = {r["id"]: r for r in _read("functions.csv")}
        self.alignments = _read("function-alignments.csv")
        self.use_cases = {r["id"]: r for r in _read("use-cases.csv")}
        self.uc_sectors = _read("use-case-sectors.csv")
        self.uc_functions = _read("use-case-functions.csv")

        self.sectors_of = {uc: [] for uc in self.use_cases}
        for row in self.uc_sectors:
            self.sectors_of.setdefault(row["use_case_id"], []).append(row["sector_id"])
        self.functions_of = {uc: [] for uc in self.use_cases}
        for row in self.uc_functions:
            self.functions_of.setdefault(row["use_case_id"], []).append(row)

    # -- derivations ----------------------------------------------------
    def section_of(self, sector_id):
        """Walk skos:broader up to the ISIC section a sector sits under."""
        seen = set()
        current = sector_id
        while current and current not in seen:
            seen.add(current)
            row = self.sectors.get(current)
            if row is None:
                return None
            if row["level"] == "section":
                return current
            current = row["broader"] or None
        return None

    def sections_of_use_case(self, uc_id):
        out = []
        for sector_id in self.sectors_of.get(uc_id, []):
            section = self.section_of(sector_id)
            if section and section not in out:
                out.append(section)
        return sorted(out, key=lambda s: self.sectors[s]["notation"])

    def scope_of(self, uc_id):
        return "CrossSector" if len(self.sections_of_use_case(uc_id)) > 1 else "SectorSpecific"

    def primary_function(self, uc_id):
        for row in self.functions_of.get(uc_id, []):
            if row["role"] == "primary":
                return row["function_id"]
        return None

    def documentation_iri(self, uc_id):
        """Absolute URL of the worked flow, wherever it happens to be published."""
        return self.use_cases[uc_id]["documented_by"].strip() or None

    # -- convenience ----------------------------------------------------
    def used_sections(self):
        used = {s for uc in self.use_cases for s in self.sections_of_use_case(uc)}
        return sorted(used, key=lambda s: self.sectors[s]["notation"])

    def used_functions(self):
        used = {r["function_id"] for r in self.uc_functions}
        return [f for f in self.functions if f in used]

    def cell(self, section_id, function_id, role=None):
        """Use cases sitting at the intersection of a section and a function."""
        out = []
        for uc in self.use_cases:
            if section_id not in self.sections_of_use_case(uc):
                continue
            for row in self.functions_of.get(uc, []):
                if row["function_id"] == function_id and (role is None or row["role"] == role):
                    out.append(uc)
                    break
        return out

    def label(self, kind, ident):
        table = {"sector": self.sectors, "function": self.functions,
                 "cbf": self.cbf, "apqc-pcf": self.apqc}[kind]
        row = table.get(ident, {})
        return row.get("pref_label_en", ident)


