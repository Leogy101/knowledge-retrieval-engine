# Licensing and attribution

KRE's original software and documentation are licensed under **Apache-2.0**.
See the complete [LICENSE](LICENSE) and [NOTICE](NOTICE).

> Copyright 2026 Brandon Gordon and KRE contributors.

The shared companion-project material listed in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)
retains its GCB attribution and Apache-2.0 terms. Referencing another project does
not assert ownership of its code, names or trademarks.

The authored documents and task text in `evaluation/large-scale-v1` retain their
existing **CC0-1.0** dedication, recorded in that fixture's README. The software
that generates or evaluates the dataset is Apache-2.0. Preserve the dedication;
do not present the entire KRE implementation as CC0. The full CC0 legal text is
included in [LICENSES/CC0-1.0.txt](LICENSES/CC0-1.0.txt).

## Distribution metadata

The wheel contains Apache-2.0 runtime software and its notices. The source
distribution and source archive additionally include the designated CC0 dataset.
Explicit `License-File` metadata includes LICENSE, NOTICE, this licensing summary,
third-party notices and the CC0 legal text. A single static `License-Expression`
is intentionally omitted because the wheel and source distribution have
different content scopes; no custom build backend is required. The license is
not unknown: the applicable terms are provided with each distribution.

This follows the [Python packaging specification](https://packaging.python.org/en/latest/specifications/pyproject-toml/#license),
which permits omitting a static expression when distributions differ. Including
CC0 legal text in the wheel does not add the dataset or relicense runtime code.
There are no installed runtime package dependencies.

## Branding

The release includes the owner-supplied KRE logo in its Apache-2.0 documentation
distribution. The original PNG and its embedded generated-media provenance are
preserved; see [asset provenance](docs/assets/README.md). No proprietary font file
or font-service dependency is included. This license grants no trademark rights
beyond those stated in Apache-2.0, and makes no ownership claim over third-party
names or embedded provider certificate material.

Version `0.3.2a1` and planned tag `v0.3.2a1` retain the established package version.
Licensing is adopted; public repository creation and release publication still
require the owner's separate authorization.
