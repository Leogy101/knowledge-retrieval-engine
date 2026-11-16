# Third-party components and attribution

KRE declares no installed runtime package dependencies. It uses Python's standard library and the SQLite library supplied by the user's Python installation. It does not bundle implementations of Python, SQLite, setuptools, Matplotlib or GitHub Actions. Shared companion-project source is attributed below; no installed GCB package is required. This notice does not change third-party licenses.

| Component | Relationship to KRE | License / authoritative reference |
|---|---|---|
| Python | User-installed runtime; not distributed inside KRE | [PSF license and incorporated software notices](https://docs.python.org/3/license.html) |
| SQLite / FTS5 | Supplied by Python's `sqlite3`; not bundled by KRE | [SQLite public-domain dedication](https://www.sqlite.org/copyright.html) |
| setuptools | Build-only package dependency; not a runtime dependency | [Project license](https://github.com/pypa/setuptools/blob/main/LICENSE) |
| Matplotlib | Optional developer-only chart reproduction tool; not a runtime dependency or bundled implementation | [Matplotlib license](https://matplotlib.org/stable/project/license.html) |
| GitHub Actions checkout / setup-python | Optional CI actions; not included in the installed package | [checkout MIT license](https://github.com/actions/checkout/blob/main/LICENSE), [setup-python MIT license](https://github.com/actions/setup-python/blob/main/LICENSE) |

The authored documents and task text in `evaluation/large-scale-v1` retain their existing **CC0-1.0** dedication. See that fixture's README and [CC0 legal code](https://creativecommons.org/publicdomain/zero/1.0/legalcode). The software that generates or evaluates a fixture is distinct from its dataset content. Preserve each applicable notice when redistributing.

The versioned context contract and examples are included for interoperability. Referencing OpenClaw, MCP, GCB, Python or SQLite describes compatibility; it does not imply endorsement or ownership of their names or code.

The initial release uses a plain-text KRE wordmark with the reader's default font. No graphical logo or proprietary font files are included. Generated benchmark charts are project-authored; the SVG uses text rather than embedded font glyphs, and the PNG is a rendered chart.

## Shared GCB material

The stdio transport and deterministic quality modules (`src/kre/_stdio.py` and
`src/kre/quality.py`), shared context contract (`contracts/context/0.1`), synthetic
efficiency examples (`docs/examples/efficiency`), and GCB-derived calibration
documentation (`tests/fixtures/calibration/gcb-mcp.md`) contain shared companion-project
material licensed under Apache-2.0:

> Governed Capability Broker (GCB)  
> Copyright 2026 Brandon Gordon and GCB contributors.

The common module-entry pattern is also shared. This attribution does not assert
the direction of copying or exclusive KRE authorship. See [NOTICE](NOTICE) and the
[GCB project](https://github.com/Leogy101/governed-capability-broker). Frozen fixture
bytes remain unchanged; notices are supplied separately.

Original KRE software and documentation are Apache-2.0. See [LICENSING.md](LICENSING.md)
for the scope of the designated CC0 dataset and artifact metadata.
