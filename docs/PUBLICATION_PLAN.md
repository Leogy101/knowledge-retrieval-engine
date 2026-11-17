# Publication procedure — execution is not authorized

Destination: **`Leogy101/knowledge-retrieval-engine`**. Version: **`0.3.2a1`**.
Future tag: **`v0.3.2a1`**. The prepared source adopts Apache-2.0 and the owner-supplied KRE
logo. This document grants no permission to create a repository, change GitHub
settings, push, tag or publish. **No PyPI publication is included.**

Prepared repository description:

> Harness-agnostic AI knowledge retrieval and context management. Delivers relevant, provenance-aware context while reducing token waste and preserving task continuity. Pairs well with Governed Capability Broker (GCB).

Retain the README's limits: experimental local lexical retrieval, provenance and
explicit task continuity; general quality-preserving token/cost savings remain
unproven. Independent human semantic judgments remain pending. A new model campaign
is not required for this narrow alpha scope. GCB and live assistant/model
configurations are outside this procedure.

## 1. Review the source candidate

Review the final inventory, attribution, license, README, evidence limitations and
local verification before authorizing **repository creation, source push and
private vulnerability reporting**. Preserve private development history separately.
Publish only the prepared new-root repository; never merge private ancestry, add a
private remote, mirror a repository or push all refs.

Run these commands in Bash from the prepared checkout. Substitute the final commit
for `REVIEWED_SHA` in the execution record. Leave the placeholder in this versioned
document: embedding its own commit SHA would change it. Retain verification
evidence outside the checkout.

```bash
set -euo pipefail
KRE_REPO=Leogy101/knowledge-retrieval-engine
KRE_GH_REPO=github.com/$KRE_REPO
KRE_VERSION=0.3.2a1
KRE_TAG=v$KRE_VERSION
REVIEWED_SHA=REPLACE_WITH_REVIEWED_40_CHARACTER_COMMIT_SHA
KRE_EVIDENCE=$(mktemp -d)
test "$REVIEWED_SHA" = "$(git rev-parse HEAD)"
test "$(git branch --show-current)" = main
test -z "$(git status --porcelain)"
test -z "$(git remote)"
test -z "$(git tag --list)"
test "$(git rev-list --count --all)" = 1
test "$(git rev-list --max-parents=0 HEAD)" = "$REVIEWED_SHA"
git show --no-patch --format=fuller "$REVIEWED_SHA"
git ls-tree -r --name-only "$REVIEWED_SHA"
test -f LICENSE
test -f NOTICE
python3 scripts/release_check.py
gh auth status --hostname github.com
test "$(gh api --hostname github.com user --jq .login)" = Leogy101
```

Confirm the public author/committer identity is intentional and the inventory
matches the reviewed allowlist. Signature checks do not replace content review.

## 2. Authorized source publication only

**Stop until explicit authorization covers this section.** Create an empty public
repository without `--push`, an added README, license template or tag. If the
destination already exists, stop and inspect ownership, refs and scope; do not
overwrite it. [The CLI documents repository creation flags.](https://cli.github.com/manual/gh_repo_create)

```bash
GH_HOST=github.com gh repo create "$KRE_REPO" --public --source . --remote origin \
  --description 'Harness-agnostic AI knowledge retrieval and context management. Delivers relevant, provenance-aware context while reducing token waste and preserving task continuity. Pairs well with Governed Capability Broker (GCB).'
case "$(git remote get-url origin)" in
  "https://github.com/$KRE_REPO.git"|"git@github.com:$KRE_REPO.git") ;;
  *) echo 'Unexpected origin; stop.' >&2; exit 1 ;;
esac
test "$(git remote get-url --push origin)" = "$(git remote get-url origin)"
gh repo view "$KRE_GH_REPO" --json nameWithOwner,url,isPrivate,isFork,viewerPermission
test "$(gh api --hostname github.com "repos/$KRE_REPO" --jq '[.full_name,.visibility,.fork,.permissions.admin]|@tsv')" = $'Leogy101/knowledge-retrieval-engine\tpublic\tfalse\ttrue'
test -z "$(git ls-remote --heads --tags origin)"
test "$REVIEWED_SHA" = "$(git rev-parse HEAD)"
git -c push.followTags=false push --set-upstream origin HEAD:refs/heads/main
test "$(git ls-remote origin refs/heads/main | cut -f1)" = "$REVIEWED_SHA"
test -z "$(git ls-remote --tags origin)"
test "$(gh api --hostname github.com "repos/$KRE_REPO" --jq .default_branch)" = main
```

Immediately enable private vulnerability reporting and require a `true` readback.
GitHub documents the [enable and status endpoints](https://docs.github.com/en/rest/repos/repos#enable-private-vulnerability-reporting-for-a-repository).

```bash
gh api --hostname github.com --method PUT "repos/$KRE_REPO/private-vulnerability-reporting" --silent
test "$(gh api --hostname github.com "repos/$KRE_REPO/private-vulnerability-reporting" --jq .enabled)" = true
gh repo view "$KRE_GH_REPO" --json isSecurityPolicyEnabled,securityPolicyUrl
```

Verify **Security → Security policy** displays this policy and **Report a
vulnerability** opens the private form. Do not submit a test report. Resolve
missing settings or policy visibility before progressing.

## 3. Require all declared CI jobs on the reviewed commit

The workflow runs on `main` and version-tag pushes and declares **13 jobs**: eight full offline suites on
`ubuntu-latest`/`macos-15` × Python 3.11–3.14; four Windows portable-core jobs
on Python 3.11–3.14; one Ubuntu artifact job on Python 3.14. Declarations are not
execution results. Windows does not support protected file ingestion.

Select the exact commit's push run. If it has not appeared, repeat the list command.
Wait for completion using `gh run watch` if the active credential supports it, or
inspect `gh run view` until completed. `gh run view --exit-status` alone does not
prove completion. See GitHub's [run filters](https://cli.github.com/manual/gh_run_list),
[run inspection](https://cli.github.com/manual/gh_run_view) and
[job results](https://docs.github.com/en/rest/actions/workflow-jobs#list-jobs-for-a-workflow-run).

```bash
KRE_RUN_ID=$(gh run list -R "$KRE_GH_REPO" --workflow ci.yml --branch main \
  --event push --commit "$REVIEWED_SHA" --limit 1 --json databaseId --jq '.[0].databaseId // empty')
test -n "$KRE_RUN_ID"
gh run view "$KRE_RUN_ID" -R "$KRE_GH_REPO" --json headSha,headBranch,event,status,conclusion,url,jobs > "$KRE_EVIDENCE/ci-run.json"
gh api --hostname github.com "repos/$KRE_REPO/actions/runs/$KRE_RUN_ID/jobs?filter=latest&per_page=100" > "$KRE_EVIDENCE/ci-jobs.json"
python3 - "$REVIEWED_SHA" "$KRE_EVIDENCE" <<'PY'
import json, pathlib, sys
sha, folder = sys.argv[1], pathlib.Path(sys.argv[2])
run = json.loads((folder / 'ci-run.json').read_text())
jobs = json.loads((folder / 'ci-jobs.json').read_text())['jobs']
expected = {f'Full offline suite ({os}, Python {v})'
            for os in ('ubuntu-latest', 'macos-15')
            for v in ('3.11', '3.12', '3.13', '3.14')}
expected |= {f'Portable core only (Windows, Python {v})'
             for v in ('3.11', '3.12', '3.13', '3.14')}
expected.add('Build and install release candidate artifacts')
assert (run['headSha'], run['headBranch'], run['event']) == (sha, 'main', 'push')
assert (run['status'], run['conclusion']) == ('completed', 'success')
assert len(jobs) == len(expected) and {j['name'] for j in jobs} == expected
for job in jobs:
    assert job['head_sha'] == sha
    assert (job['status'], job['conclusion']) == ('completed', 'success')
    assert job['steps'] and all(s['status'] == 'completed' and s['conclusion'] == 'success'
                               for s in job['steps'])
    print(job['name'], job['labels'], job['runner_name'], job['html_url'])
print('All 13 declared jobs and their steps passed for', sha)
PY
gh run view "$KRE_RUN_ID" -R "$KRE_GH_REPO" --log > "$KRE_EVIDENCE/ci.log"
```

Inspect logs for actual runner OS/image, architecture, Python/SQLite versions,
test counts and skips. Report actual platforms; `*-latest` is not a fixed OS.
Missing, cancelled, skipped, neutral or failing required jobs/steps block release.
Do not add skips, exclusions, `continue-on-error` or weaker security checks to make
CI green. Fix the cause in sanitized history, refresh the manifest, review the new
commit, update `REVIEWED_SHA`, push only `main`, and repeat CI and subsequent checks.
The one-commit check applies before first publication; reviewed fixes may add commits.

## 4. Verify a fresh public clone and installed MCP workflow

On a supported POSIX machine, clone public HTTPS without Git credential helpers,
global configuration or interactive authentication. Verify the commit, manifest
and rendered README, including links, diagram and licensing.

```bash
KRE_WORK=$(mktemp -d)
KRE_CLONE=$KRE_WORK/source
GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null GIT_TERMINAL_PROMPT=0 \
  git -c credential.helper= -c http.extraHeader= clone --no-tags --single-branch \
  --branch main "https://github.com/$KRE_REPO.git" "$KRE_CLONE"
test "$(git -C "$KRE_CLONE" rev-parse HEAD)" = "$REVIEWED_SHA"
(cd "$KRE_CLONE" && python3 scripts/release_check.py)
python3 -m venv "$KRE_WORK/source-venv"
KRE_PY=$KRE_WORK/source-venv/bin/python
"$KRE_PY" -m pip install "$KRE_CLONE"
mkdir "$KRE_WORK/quickstart"
(
  cd "$KRE_WORK/quickstart"
  KRE_CLI=$KRE_WORK/source-venv/bin/kre
  "$KRE_CLI" --version
  "$KRE_CLI" demo
  "$KRE_CLI" search rollback
  "$KRE_CLI" context rollback --budget 3000 --max-bytes 3000
  "$KRE_CLI" demo-k2
)
"$KRE_PY" -I "$KRE_CLONE/scripts/verify_user_workflow.py" > "$KRE_EVIDENCE/public-clone-workflow.json"
```

Require `status: passed`, version `0.3.2a1` and every workflow check. This exercises
installed ingestion, exact citations, updates, revocation, task continuity, MCP
stdio discovery/retrieval/validation and scope denial using temporary synthetic
data. It makes no inference calls or live host configuration changes.

## 5. Build and qualify the exact release assets

Build at `REVIEWED_SHA` from the public clone into an empty directory. The wheel,
sdist and source archive must have the adopted `LICENSE`/`NOTICE`, consistent
version metadata, only reviewed payloads and no private paths, credentials,
databases or private Git history. Inspect generated metadata too.

```bash
KRE_ASSETS=$KRE_WORK/assets
mkdir "$KRE_ASSETS"
"$KRE_PY" -m pip install build
"$KRE_PY" -m build --outdir "$KRE_ASSETS" "$KRE_CLONE"
git -C "$KRE_CLONE" archive --format=tar.gz \
  --prefix="knowledge-retrieval-engine-$KRE_VERSION/" \
  --output="$KRE_ASSETS/knowledge-retrieval-engine-$KRE_VERSION-source.tar.gz" "$REVIEWED_SHA"
"$KRE_PY" "$KRE_CLONE/scripts/normalize_sdist.py" "$KRE_ASSETS"/*.tar.gz
KRE_WHEEL=$KRE_ASSETS/knowledge_retrieval_engine-$KRE_VERSION-py3-none-any.whl
KRE_SDIST=$KRE_ASSETS/knowledge_retrieval_engine-$KRE_VERSION.tar.gz
KRE_SOURCE=$KRE_ASSETS/knowledge-retrieval-engine-$KRE_VERSION-source.tar.gz
"$KRE_PY" -m zipfile -l "$KRE_WHEEL"
tar -tvzf "$KRE_SDIST"
tar -tvzf "$KRE_SOURCE"
```

Compare extracted payloads to the reviewed source manifest and inspect every extra
generated file. Require safe relative regular-file/directory archive members,
normalized tar ownership/timestamps, no symlinks and no unexpected files. Preserve
this artifact audit with the CI/clone evidence. The source checker alone cannot
establish artifact cleanliness. Independently install both formats:

```bash
for KRE_KIND in wheel sdist; do
  python3 -m venv "$KRE_WORK/$KRE_KIND-venv"
  KRE_TEST_PY=$KRE_WORK/$KRE_KIND-venv/bin/python
  if [ "$KRE_KIND" = wheel ]; then
    "$KRE_TEST_PY" -m pip install --no-index --no-deps "$KRE_WHEEL"
  else
    "$KRE_TEST_PY" -m pip install --no-deps "$KRE_SDIST"
  fi
  "$KRE_TEST_PY" -I -c "import kre, importlib.metadata as m; assert kre.__version__ == m.version('knowledge-retrieval-engine') == '0.3.2a1'"
  "$KRE_TEST_PY" -I "$KRE_CLONE/scripts/verify_user_workflow.py" > "$KRE_EVIDENCE/$KRE_KIND-workflow.json"
  "$KRE_TEST_PY" -m pip uninstall -y knowledge-retrieval-engine
  "$KRE_TEST_PY" -I -c "import importlib.util; assert importlib.util.find_spec('kre') is None"
done
python3 - "$KRE_ASSETS" <<'PY'
import hashlib, pathlib, sys
folder = pathlib.Path(sys.argv[1])
files = sorted(folder.iterdir())
assert len(files) == 3 and all(p.is_file() for p in files)
(folder / 'SHA256SUMS').write_text(''.join(
    f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n' for p in files))
PY
```

Building and sdist installation may download build dependencies; installed KRE
needs no runtime dependencies. Retain the three inspected assets/checksums
unchanged. Any source correction restarts qualification at the new SHA.

## 6. Separately authorize the tag and experimental GitHub release

**Stop until the owner approves** the qualified commit, actual CI/platform report,
public clone/MCP results, private-reporting verification, artifact audit, checksums
and release notes for tag/release publication. Do not upload assets or create even
a draft release before authorization. Verify `main` still matches and use an
annotated tag with `--verify-tag`, which prevents release creation from silently
selecting another commit. [GitHub documents these release flags.](https://cli.github.com/manual/gh_release_create)

```bash
test "$(git ls-remote origin refs/heads/main | cut -f1)" = "$REVIEWED_SHA"
test "$(gh api --hostname github.com "repos/$KRE_REPO/private-vulnerability-reporting" --jq .enabled)" = true
test -z "$(git ls-remote --tags origin "refs/tags/$KRE_TAG" "refs/tags/$KRE_TAG^{}")"
test "$(git -C "$KRE_CLONE" rev-parse HEAD)" = "$REVIEWED_SHA"
git -C "$KRE_CLONE" diff --quiet HEAD
(cd "$KRE_CLONE" && python3 scripts/release_check.py)
python3 - "$KRE_ASSETS" <<'PY'
import hashlib, pathlib, sys
folder = pathlib.Path(sys.argv[1])
for line in (folder / 'SHA256SUMS').read_text().splitlines():
    digest, name = line.split('  ', 1)
    assert hashlib.sha256((folder / name).read_bytes()).hexdigest() == digest
PY
git tag -a "$KRE_TAG" "$REVIEWED_SHA" -m "KRE $KRE_VERSION experimental alpha"
git -c push.followTags=false push origin "refs/tags/$KRE_TAG:refs/tags/$KRE_TAG"
test "$(git ls-remote origin "refs/tags/$KRE_TAG^{}" | cut -f1)" = "$REVIEWED_SHA"
# Before running release create, require the version tag's distinct push run:
# gh run list -R "$KRE_GH_REPO" --workflow ci.yml --branch "$KRE_TAG" --event push --commit "$REVIEWED_SHA"
# Reuse section 3's 13-job/step checks, expecting headBranch == "$KRE_TAG".
# Do not publish if tag CI is incomplete or fails.
gh release create "$KRE_TAG" -R "$KRE_GH_REPO" --verify-tag --prerelease --latest=false \
  --title "KRE $KRE_VERSION — experimental alpha" \
  --notes-file "$KRE_CLONE/docs/RELEASE_NOTES.md" \
  "$KRE_WHEEL" "$KRE_SDIST" "$KRE_SOURCE" "$KRE_ASSETS/SHA256SUMS"
gh release view "$KRE_TAG" -R "$KRE_GH_REPO" \
  --json url,tagName,isDraft,isPrerelease,targetCommitish,assets
mkdir "$KRE_WORK/downloaded"
gh release download "$KRE_TAG" -R "$KRE_GH_REPO" --dir "$KRE_WORK/downloaded"
python3 - "$KRE_WORK/downloaded" "$KRE_ASSETS/SHA256SUMS" <<'PY'
import hashlib, pathlib, sys
folder, original = map(pathlib.Path, sys.argv[1:])
assert (folder / 'SHA256SUMS').read_bytes() == original.read_bytes()
for line in original.read_text().splitlines():
    digest, name = line.split('  ', 1)
    assert hashlib.sha256((folder / name).read_bytes()).hexdigest() == digest
print('Downloaded release assets match approved checksums.')
PY
```

Confirm a published prerelease, all four named assets, the peeled tag pointing to
`REVIEWED_SHA`, and working public README/security links. Record final URLs and
retain the evidence. Do not publish to PyPI or change GCB.
