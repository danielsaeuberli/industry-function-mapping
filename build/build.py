#!/usr/bin/env python3
"""Generate the Industry-Function Mapping knowledge graph and its matrix views.

    python3 build/build.py            # write generated/
    python3 build/build.py --check    # fail if generated/ is stale (used in CI)

Inputs are the CSVs in data/; nothing in generated/ should ever be hand-edited.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from model import BASE, GENERATED_DIR, ID_BASE, ONT, SCHEMES, Model  # noqa: E402

PREFIXES = [
    ("ifm", ONT),
    ("scheme", ID_BASE + "scheme/"),
    ("sector", ID_BASE + "sector/"),
    ("func", ID_BASE + "function/"),
    ("cbf", ID_BASE + "cbf/"),
    ("apqc", ID_BASE + "apqc/"),
    ("uc", ID_BASE + "use-case/"),
    ("skos", "http://www.w3.org/2004/02/skos/core#"),
    ("schema", "https://schema.org/"),
    ("dct", "http://purl.org/dc/terms/"),
    ("rdfs", "http://www.w3.org/2000/01/rdf-schema#"),
    ("owl", "http://www.w3.org/2002/07/owl#"),
    ("xsd", "http://www.w3.org/2001/XMLSchema#"),
]


# --------------------------------------------------------------------------
# One graph, two serialisations
#
# The blocks below are the single source of truth for both ifm-graph.ttl and
# ifm-graph.jsonld, so the two files can never drift apart. A block is
# (subject, [(predicate, [object, ...]), ...]); objects are Ref or Lit.
# --------------------------------------------------------------------------

class Ref(str):
    """A prefixed name (sector:ISIC-C) or an absolute IRI (<https://...>)."""


class Lit:
    def __init__(self, value, lang="en"):
        self.value = str(value)
        self.lang = lang

    def turtle(self):
        text = (self.value.replace("\\", "\\\\").replace('"', '\\"')
                .replace("\n", "\\n").replace("\r", ""))
        return f'"{text}"@{self.lang}' if self.lang else f'"{text}"'


def L(value, lang="en"):
    return [Lit(value, lang)] if value else []


def R(ref):
    return [Ref(ref)] if ref else []


# Turtle prefixed names cannot contain "/", so each layer gets its own prefix
# rather than one namespace with slash-separated local names.
PREFIX_OF_KIND = {
    "sector": "sector",
    "function": "func",
    "cbf": "cbf",
    "apqc": "apqc",
    "use-case": "uc",
}


def scheme_iri(scheme_id):
    return f"scheme:{scheme_id}"


def concept_ref(kind, ident):
    return f"{PREFIX_OF_KIND[kind]}:{ident}"


def graph_blocks(model):
    """Yield (heading, subject, pairs) for every node in the graph."""
    blocks = []

    blocks.append(("Concept schemes", Ref(f"<{BASE}>"), [
        ("a", R("owl:Ontology")),
        ("owl:imports", R(f"<{BASE}ontology>")),
        ("dct:title", L("Industry-Function Mapping graph")),
        ("dct:creator", L("Daniel Saeuberli", lang=None)),
        ("dct:license", R("<https://creativecommons.org/licenses/by/4.0/>")),
    ]))
    for scheme_id, meta in SCHEMES.items():
        blocks.append(("Concept schemes", Ref(scheme_iri(scheme_id)), [
            ("a", R("skos:ConceptScheme")),
            ("dct:title", L(meta["title"])),
            ("dct:description", L(meta["description"])),
            ("dct:source", R(f"<{meta['source']}>")),
        ]))

    heading = "Layer 1 - Sectors (ISIC Rev. 4)"
    for sector_id, row in model.sectors.items():
        narrower = [Ref(concept_ref("sector", other_id))
                    for other_id, other in model.sectors.items()
                    if other["broader"] == sector_id]
        blocks.append((heading, Ref(concept_ref("sector", sector_id)), [
            ("a", [Ref("ifm:Sector"), Ref("skos:Concept")]),
            ("skos:inScheme", R(scheme_iri("isic-rev4"))),
            ("skos:topConceptOf", R(scheme_iri("isic-rev4")) if not row["broader"] else []),
            ("skos:prefLabel", L(row["pref_label_en"])),
            ("skos:notation", L(row["notation"], lang=None)),
            ("skos:broader", R(concept_ref("sector", row["broader"])) if row["broader"] else []),
            ("skos:narrower", narrower),
            ("ifm:naceRev2Code", L(row["nace_rev2"], lang=None)),
            ("ifm:codeStatus", L(row["code_status"], lang=None)),
            ("skos:scopeNote", L(row["note"])),
        ]))

    heading = "Layer 2a - CBF categories (mapping target)"
    for cbf_id, row in model.cbf.items():
        blocks.append((heading, Ref(concept_ref("cbf", cbf_id)), [
            ("a", R("skos:Concept")),
            ("skos:inScheme", R(scheme_iri("cbf"))),
            ("skos:topConceptOf", R(scheme_iri("cbf")) if not row["broader"] else []),
            ("skos:prefLabel", L(row["pref_label_en"])),
            ("skos:broader", R(concept_ref("cbf", row["broader"])) if row["broader"] else []),
            ("skos:definition", L(row["definition"])),
            ("ifm:codeStatus", L(row["code_status"], lang=None)),
        ]))

    heading = "Layer 2b - APQC PCF categories (mapping target)"
    for apqc_id, row in model.apqc.items():
        blocks.append((heading, Ref(concept_ref("apqc", apqc_id)), [
            ("a", R("skos:Concept")),
            ("skos:inScheme", R(scheme_iri("apqc-pcf"))),
            ("skos:topConceptOf", R(scheme_iri("apqc-pcf"))),
            ("skos:prefLabel", L(row["pref_label_en"])),
            ("skos:notation", L(row["notation"], lang=None)),
            ("ifm:codeStatus", L(row["code_status"], lang=None)),
            ("skos:scopeNote", L(row["note"])),
        ]))

    heading = "Layer 2c - Operational business functions (+ alignments)"
    kind_of_scheme = {"cbf": "cbf", "apqc-pcf": "apqc"}
    for function_id, row in model.functions.items():
        matches = {}
        notes = []
        for alignment in model.alignments:
            if alignment["function_id"] != function_id:
                continue
            ref = Ref(concept_ref(kind_of_scheme[alignment["target_scheme"]],
                                  alignment["target_id"]))
            matches.setdefault(f"skos:{alignment['match_type']}", []).append(ref)
            notes += L(alignment["note"])
        narrower = [Ref(concept_ref("function", other_id))
                    for other_id, other in model.functions.items()
                    if other["broader"] == function_id]
        pairs = [
            ("a", [Ref("ifm:BusinessFunction"), Ref("skos:Concept")]),
            ("skos:inScheme", R(scheme_iri("ifm-functions"))),
            ("skos:topConceptOf", R(scheme_iri("ifm-functions")) if not row["broader"] else []),
            ("skos:prefLabel", L(row["pref_label_en"])),
            ("skos:definition", L(row["definition"])),
            ("skos:broader", R(concept_ref("function", row["broader"])) if row["broader"] else []),
            ("skos:narrower", narrower),
        ]
        for match_type in ("skos:exactMatch", "skos:closeMatch",
                           "skos:broadMatch", "skos:relatedMatch"):
            pairs.append((match_type, matches.get(match_type, [])))
        pairs.append(("skos:editorialNote", notes))
        blocks.append((heading, Ref(concept_ref("function", function_id)), pairs))

    heading = "Layer 3 - Use cases (sector x function intersection nodes)"
    for uc_id, row in model.use_cases.items():
        primary = model.primary_function(uc_id)
        supporting = [r["function_id"] for r in model.functions_of[uc_id]
                      if r["role"] != "primary"]
        documentation = model.documentation_iri(uc_id)
        blocks.append((heading, Ref(concept_ref("use-case", uc_id)), [
            ("a", [Ref("ifm:UseCase"), Ref("schema:Action")]),
            ("schema:name", L(row["name"])),
            ("schema:description", L(row["description"])),
            ("ifm:appliesToSector", [Ref(concept_ref("sector", s))
                                     for s in model.sectors_of[uc_id]]),
            ("ifm:primaryFunction", R(concept_ref("function", primary)) if primary else []),
            ("ifm:executesFunction", [Ref(concept_ref("function", f)) for f in supporting]),
            ("ifm:sectorScope", R(f"ifm:{model.scope_of(uc_id)}")),
            ("ifm:maturity", R(f"ifm:{row['maturity']}")),
            ("ifm:documentedBy", R(f"<{documentation}>") if documentation else []),
        ]))

    return blocks


def build_turtle(model):
    blocks = graph_blocks(model)
    out = [
        "# Industry-Function Mapping - generated knowledge graph.",
        "# DO NOT EDIT: regenerate with `python3 build/build.py` from data/*.csv.",
        f"# {len(model.use_cases)} use cases, {len(model.sectors)} sector concepts, "
        f"{len(model.functions)} function concepts.",
        "# SPDX-License-Identifier: CC-BY-4.0",
        "",
    ]
    out += [f"@prefix {prefix}: <{uri}> ." for prefix, uri in PREFIXES]
    out.append("")

    current_heading = None
    for heading, subject, pairs in blocks:
        if heading != current_heading:
            current_heading = heading
            out += ["#" * 70, f"# {heading}", "#" * 70, ""]
        kept = [(predicate, objects) for predicate, objects in pairs if objects]
        lines = [str(subject)]
        for index, (predicate, objects) in enumerate(kept):
            rendered = ", ".join(o if isinstance(o, Ref) else o.turtle() for o in objects)
            terminator = " ;" if index < len(kept) - 1 else " ."
            lines.append(f"    {predicate} {rendered}{terminator}")
        out.append("\n".join(lines))
        out.append("")

    return "\n".join(out).rstrip() + "\n"


def build_jsonld(model):
    """Expanded-by-prefix JSON-LD: same triples as the Turtle, key for key."""
    context = {prefix: uri for prefix, uri in PREFIXES}
    context["@vocab"] = ONT

    nodes = []
    for _heading, subject, pairs in graph_blocks(model):
        subject_id = str(subject)
        if subject_id.startswith("<"):
            subject_id = subject_id[1:-1]
        node = {"@id": subject_id}
        for predicate, objects in pairs:
            if not objects:
                continue
            key = "@type" if predicate == "a" else predicate
            values = []
            for obj in objects:
                if isinstance(obj, Ref):
                    ref = str(obj)
                    ref = ref[1:-1] if ref.startswith("<") else ref
                    values.append(ref if key == "@type" else {"@id": ref})
                elif obj.lang:
                    values.append({"@value": obj.value, "@language": obj.lang})
                else:
                    values.append({"@value": obj.value})
            node[key] = values[0] if len(values) == 1 and key != "@type" else values
        nodes.append(node)

    return json.dumps({"@context": context, "@graph": nodes}, indent=2,
                      ensure_ascii=False) + "\n"


# --------------------------------------------------------------------------
# Matrix views
# --------------------------------------------------------------------------

def matrix_rows(model):
    sections = model.used_sections()
    functions = model.used_functions()
    grid = {}
    for section in sections:
        for function in functions:
            primary = model.cell(section, function, role="primary")
            supporting = [uc for uc in model.cell(section, function) if uc not in primary]
            grid[(section, function)] = (primary, supporting)
    return sections, functions, grid


def build_matrix_md(model):
    sections, functions, grid = matrix_rows(model)
    lines = [
        "<!-- DO NOT EDIT: generated by build/build.py -->",
        "# Sector x function matrix",
        "",
        "Rows are ISIC Rev. 4 sections, columns are business functions. "
        "`#` marks a use case where the function is the primary one, "
        "`.` marks a supporting function.",
        "",
    ]
    header = "| Sector | " + " | ".join(
        f"{model.label('function', f)}" for f in functions) + " |"
    lines.append(header)
    lines.append("|---|" + "---|" * len(functions))
    for section in sections:
        cells = []
        for function in functions:
            primary, supporting = grid[(section, function)]
            cells.append(("#" * len(primary)) + ("." * len(supporting)) or "")
        lines.append(f"| **{model.sectors[section]['notation']}** "
                     f"{model.label('sector', section)} | " + " | ".join(cells) + " |")

    lines += ["", "## Functions reused across sections", "",
              "This is the point of keeping functions independent of sectors: "
              "a function that appears in more than one section is a candidate "
              "for one shared pattern instead of several sector-specific ones.", ""]
    for function in functions:
        touched = [s for s in sections if model.cell(s, function)]
        if len(touched) > 1:
            codes = ", ".join(model.sectors[s]["notation"] for s in touched)
            lines.append(f"- **{model.label('function', function)}** — "
                         f"{len(touched)} sections ({codes})")

    lines += ["", "## Use cases", ""]
    for uc_id, row in model.use_cases.items():
        sector_labels = ", ".join(
            f"{model.sectors[s]['notation']} {model.label('sector', s)}"
            for s in model.sectors_of[uc_id])
        primary = model.primary_function(uc_id)
        lines.append(f"### {row['name']}")
        lines.append("")
        lines.append(f"{row['description']}")
        lines.append("")
        lines.append(f"- Sectors: {sector_labels}")
        lines.append(f"- Primary function: {model.label('function', primary)}")
        supporting = [model.label('function', r["function_id"])
                      for r in model.functions_of[uc_id] if r["role"] != "primary"]
        if supporting:
            lines.append(f"- Supporting functions: {', '.join(supporting)}")
        lines.append(f"- Scope: {'cross-sector' if model.scope_of(uc_id) == 'CrossSector' else 'sector-specific'}"
                     f" · Maturity: {row['maturity'].lower()}")
        documentation = model.documentation_iri(uc_id)
        if documentation:
            lines.append(f"- Worked flow: [{row['documented_by']}]({documentation})")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def build_html(model):
    sections, functions, grid = matrix_rows(model)
    esc = html.escape

    head = []
    for function in functions:
        head.append(f'<th class="fn"><span>{esc(model.label("function", function))}</span></th>')

    body = []
    for section in sections:
        cells = []
        for function in functions:
            primary, supporting = grid[(section, function)]
            if not primary and not supporting:
                cells.append('<td class="empty"></td>')
                continue
            marks = []
            for uc in primary:
                marks.append(f'<a class="dot primary" href="#{esc(uc)}" '
                             f'title="{esc(model.use_cases[uc]["name"])} (primary)">&#9679;</a>')
            for uc in supporting:
                marks.append(f'<a class="dot support" href="#{esc(uc)}" '
                             f'title="{esc(model.use_cases[uc]["name"])} (supporting)">&#9675;</a>')
            cells.append('<td>' + "".join(marks) + '</td>')
        label = esc(model.label("sector", section))
        code = esc(model.sectors[section]["notation"])
        body.append(f'<tr><th class="sector" scope="row"><span class="code">{code}</span> '
                    f'{label}</th>' + "".join(cells) + "</tr>")

    cards = []
    for uc_id, row in model.use_cases.items():
        primary = model.primary_function(uc_id)
        supporting = [model.label("function", r["function_id"])
                      for r in model.functions_of[uc_id] if r["role"] != "primary"]
        sector_list = ", ".join(
            f'<span class="code">{esc(model.sectors[s]["notation"])}</span> '
            f'{esc(model.label("sector", s))}' for s in model.sectors_of[uc_id])
        documentation = model.documentation_iri(uc_id)
        link = (f'<div class="flow-link"><a href="{esc(documentation)}">Worked flow &rarr;</a></div>'
                if documentation else
                '<div class="flow-link"><span class="status">Not yet modelled</span></div>')
        scope = "Cross-sector" if model.scope_of(uc_id) == "CrossSector" else "Sector-specific"
        cards.append(f"""      <div class="flow" id="{esc(uc_id)}">
        <div class="flow-tag">{esc(scope)} &middot; {esc(row['maturity'])}</div>
        <div class="flow-body">
          <h3>{esc(row['name'])}</h3>
          <p>{esc(row['description'])}</p>
          <p class="meta"><strong>Sectors:</strong> {sector_list}</p>
          <p class="meta"><strong>Primary function:</strong> {esc(model.label('function', primary))}</p>
          <p class="meta"><strong>Supporting:</strong> {esc(', '.join(supporting)) or '&mdash;'}</p>
        </div>
{link}
      </div>""")

    reused = []
    for function in functions:
        touched = [s for s in sections if model.cell(s, function)]
        if len(touched) > 1:
            codes = " ".join(f'<span class="code">{esc(model.sectors[s]["notation"])}</span>'
                             for s in touched)
            reused.append(f"<li><strong>{esc(model.label('function', function))}</strong> "
                          f"&mdash; {codes}</li>")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Industry &amp; function mapping</title>
<meta name="description" content="Which use cases sit at which intersection of economic sector (ISIC Rev. 4) and business function.">
<style>
  /* Self-contained on purpose: this page is published straight out of
     generated/ with no other assets to deploy alongside it. */
  :root {{
    --accent: #c61623; --ink: #212934; --body: #4a5261;
    --line: #e4e8ec; --bg-soft: #f8f9fb;
  }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; background: #fff; color: var(--ink); line-height: 1.6;
    font-family: -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }}
  a {{ color: var(--accent); text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}
  a:focus-visible {{ outline: 2px solid var(--accent); outline-offset: 2px; }}
  code {{ font-size: 0.92em; background: var(--bg-soft); padding: 1px 4px;
    border-radius: 3px; }}
  .wrap {{ max-width: 1040px; margin: 0 auto; padding: 0 24px; }}
  header.site {{ border-bottom: 1px solid var(--line); }}
  header.site .wrap {{ display: flex; align-items: center; justify-content: space-between;
    padding-top: 22px; padding-bottom: 22px; flex-wrap: wrap; gap: 12px; }}
  .brand {{ font-weight: 600; }}
  .divider {{ display: inline-block; width: 1px; height: 14px; margin: 0 10px -2px;
    background: var(--line); }}
  section {{ padding: 36px 0; border-top: 1px solid var(--line); }}
  section.hero {{ border-top: none; padding-bottom: 8px; }}
  h1 {{ font-size: 34px; line-height: 1.2; margin: 8px 0 16px; }}
  h2 {{ font-size: 13px; text-transform: uppercase; letter-spacing: .08em;
    color: var(--body); margin: 0 0 18px; }}
  h3 {{ font-size: 16px; margin: 0 0 8px; }}
  .eyebrow {{ font-size: 12px; text-transform: uppercase; letter-spacing: .08em;
    color: var(--accent); font-weight: 600; }}
  .lede {{ font-size: 16px; color: var(--body); max-width: 680px; }}
  .prose {{ color: var(--body); font-size: 14.5px; max-width: 680px; }}
  .matrix-scroll {{ overflow-x: auto; border: 1px solid var(--line); border-radius: 6px; }}
  table.matrix {{ border-collapse: collapse; font-size: 13px; min-width: 100%; }}
  table.matrix th, table.matrix td {{ border-bottom: 1px solid var(--line); padding: 8px 10px; }}
  table.matrix th.fn {{ vertical-align: bottom; text-align: left; font-weight: 600;
    white-space: nowrap; font-size: 12px; color: var(--body); }}
  table.matrix th.fn span {{ display: block; writing-mode: vertical-rl;
    transform: rotate(180deg); height: 185px; }}
  table.matrix th.sector {{ text-align: left; font-weight: 500; max-width: 260px;
    position: sticky; left: 0; background: #fff; border-right: 1px solid var(--line);
    line-height: 1.35; }}
  table.matrix td {{ text-align: center; vertical-align: middle; }}
  table.matrix td.empty {{ background: var(--bg-soft); }}
  .code {{ display: inline-block; min-width: 20px; padding: 0 5px; margin-right: 4px;
    border: 1px solid var(--line); border-radius: 3px; font-size: 11px;
    color: var(--body); background: var(--bg-soft); }}
  .dot {{ text-decoration: none; font-size: 13px; padding: 0 1px; }}
  .dot.primary {{ color: var(--accent); }}
  .dot.support {{ color: #9aa3b0; }}
  .legend {{ font-size: 13px; color: var(--body); margin-top: 12px; }}
  .meta {{ font-size: 13px; color: var(--body); margin: 4px 0; }}
  .flows {{ display: grid; gap: 16px; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); }}
  .flow {{ border: 1px solid var(--line); border-radius: 6px; display: flex;
    flex-direction: column; scroll-margin-top: 20px; }}
  .flow-tag {{ font-size: 11px; text-transform: uppercase; letter-spacing: .06em;
    color: var(--body); padding: 10px 16px; border-bottom: 1px solid var(--line);
    background: var(--bg-soft); }}
  .flow-body {{ padding: 16px; flex: 1; }}
  .flow-body p {{ font-size: 14px; color: var(--body); margin-top: 0; }}
  .flow-link {{ padding: 12px 16px; border-top: 1px solid var(--line); font-size: 14px; }}
  .status {{ font-size: 12px; color: var(--body); }}
  footer.site {{ border-top: 1px solid var(--line); margin-top: 40px; }}
  footer.site .wrap {{ display: flex; flex-wrap: wrap; gap: 10px 24px;
    justify-content: space-between; padding-top: 20px; padding-bottom: 40px;
    font-size: 12.5px; color: var(--body); }}
  @media (max-width: 620px) {{
    h1 {{ font-size: 27px; }}
    table.matrix th.sector {{ max-width: 160px; }}
  }}
</style>
</head>
<body>

<header class="site">
  <div class="wrap">
    <div class="brand">Industry &amp; function mapping <span class="divider"></span>
      <span style="font-weight:400;color:var(--body)">knowledge graph</span></div>
    <nav><a href="https://github.com/danielsaeuberli/industry-function-mapping">GitHub &#8599;</a></nav>
  </div>
</header>

<div class="wrap">

  <section class="hero" style="border-top:none;">
    <span class="eyebrow">Knowledge graph</span>
    <h1>Which function, in which sector</h1>
    <p class="lede">
      Every use case in this graph sits at an intersection: an economic sector
      (ISIC Rev. 4) and a business function that is defined independently of it.
      Read the matrix down a column to find the same function recurring across
      sectors &mdash; those are the places where one pattern can serve many industries.
    </p>
  </section>

  <section>
    <h2>Sector &times; function</h2>
    <div class="matrix-scroll">
      <table class="matrix">
        <thead><tr><th class="sector">ISIC Rev. 4 section</th>{''.join(head)}</tr></thead>
        <tbody>
{chr(10).join(body)}
        </tbody>
      </table>
    </div>
    <p class="legend">
      <span class="dot primary">&#9679;</span> primary function of a use case &nbsp;&middot;&nbsp;
      <span class="dot support">&#9675;</span> supporting function. Follow a marker to the use case.
    </p>
  </section>

  <section>
    <h2>Functions that recur across sectors</h2>
    <ul>
{chr(10).join(reused)}
    </ul>
  </section>

  <section>
    <h2>Use cases</h2>
    <div class="flows">
{chr(10).join(cards)}
    </div>
  </section>

  <section>
    <h2>The graph itself</h2>
    <p class="prose">
      This page is generated from the same data as the machine-readable graph:
      SKOS concept schemes for the sector and function layers, and use cases as
      <code>schema:Action</code> nodes linking the two. Load
      <a href="ifm-graph.ttl">ifm-graph.ttl</a> or
      <a href="ifm-graph.jsonld">ifm-graph.jsonld</a> into any triple store, or read the
      <a href="https://github.com/danielsaeuberli/industry-function-mapping">source data and build script</a>.
    </p>
  </section>

</div>

<footer class="site">
  <div class="wrap">
    <span>industry-function-mapping</span>
    <span>Generated from <code>data/</code> &mdash; do not edit by hand</span>
    <span><a href="https://github.com/danielsaeuberli/industry-function-mapping">Source on GitHub</a></span>
  </div>
</footer>

</body>
</html>
"""


# --------------------------------------------------------------------------

OUTPUTS = {
    "ifm-graph.ttl": build_turtle,
    "ifm-graph.jsonld": build_jsonld,
    "matrix.md": build_matrix_md,
    "index.html": build_html,
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="verify generated/ matches data/ instead of writing")
    args = parser.parse_args()

    model = Model()
    os.makedirs(GENERATED_DIR, exist_ok=True)
    stale = []
    for name, builder in OUTPUTS.items():
        content = builder(model)
        path = os.path.join(GENERATED_DIR, name)
        if args.check:
            current = open(path, encoding="utf-8").read() if os.path.exists(path) else None
            if current != content:
                stale.append(name)
            continue
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content)
        print(f"wrote generated/{name} ({len(content):,} bytes)")

    if args.check:
        if stale:
            print("stale generated files: " + ", ".join(stale), file=sys.stderr)
            print("run: python3 build/build.py", file=sys.stderr)
            return 1
        print("generated/ is up to date")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
