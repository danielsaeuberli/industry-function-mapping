# Third-Party Content Notices

This repository's own content is licensed [CC BY 4.0](LICENSE-CONTENT) and its
build scripts [MIT](LICENSE). Nothing below is covered by either grant.

This repository renders parts of several statistical classifications as SKOS
concepts so that use cases can be filed against them. Only the codes and titles
needed for the mapped use cases are carried, with attribution; **none of these
classifications is reproduced in full, and none of them is redistributed as a
dataset.** Each remains under the terms of its publisher.

| Source | Terms | Used in |
|---|---|---|
| [ISIC Rev. 4](https://unstats.un.org/unsd/classifications/Econ/isic) (United Nations Statistics Division) | UN publication; codes and titles referenced with attribution, not reproduced in full | `data/sectors.csv` — the sector layer (`skos:notation`) |
| [NACE Rev. 2](https://ec.europa.eu/eurostat/web/nace) (Eurostat) | European Commission / Eurostat; codes referenced with attribution | `data/sectors.csv` — `ifm:naceRev2Code`, at section and division level only |
| [Classification of Business Functions](https://unece.org/trade/statistics) (UNECE / Eurostat) | Referenced with attribution; labels here are marked `codeStatus "provisional"` until checked against the official publication | `data/cbf.csv` — mapping target for the function layer |
| [APQC Process Classification Framework](https://www.apqc.org/process-frameworks) (APQC) | Published by APQC under its own terms; **not redistributed here** — only the category numbers and names an alignment references are carried, marked `codeStatus "provisional"` | `data/apqc-pcf.csv` — mapping target for the function layer |

Every concept carries an `ifm:codeStatus` saying how far it has been checked
against the official publication. See [README.md](README.md) § "Provenance and
honesty".

## Use cases referenced

Six of the seeded use cases in `data/use-cases.csv` link to trust flow diagrams
in the [DIDAS Trust Flow Diagram Repository](https://github.com/DIDAS-swiss/Trust-Flow-Diagram-Repository),
which publishes them under [CC BY 4.0](https://github.com/DIDAS-swiss/Trust-Flow-Diagram-Repository/blob/main/LICENSE-CONTENT).
The diagrams themselves are not copied here — `documented_by` is a link, and the
descriptions in this repository are its own summaries.

Those diagrams are not official flows of the swiyu team, the Swiss
Confederation, or any other authority.
