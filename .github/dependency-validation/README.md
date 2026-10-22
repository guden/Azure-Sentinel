# PR #15 dependency compatibility review

Reviewed 22 October 2026. Original head: `0e640b274ed6d3ef2fe1c689820275b3fb3cbb41`.
Base: `207f43599c98a9f8c83c396e9bdc7181affd83f2`.

**Do not merge yet.** GitHub mergeability only establishes that the branches can be combined.
At the reviewed head, commit statuses, check runs and PR-triggered workflow runs were empty.
No existing Python connector tests were found for these affected connectors.

## Runtime gate

All nine distinct deployment templates serving the ten requirements files select `python|3.8`.
The AWS template additionally uses Functions `~3`; Snowflake uses `~4`.
Package metadata from the exact PyPI releases requires:

| Package | Minimum Python |
|---|---|
| aiohttp 3.14.3 | 3.10 |
| cryptography 50.0.0 | 3.9, excluding 3.9.0 and 3.9.1 |
| PyJWT 2.15.0 | 3.9 |
| snowflake-connector-python 3.18.1 | 3.9 |

`uv pip compile --python-version 3.8` failed for all ten original files.
A Python 3.11.17 probe resolved nine files; AWS failed independently on conflicting pins.
These Python 3.11 results DO NOT validate the existing Python 3.8 deployments.
Microsoft's supported runtime list must also be checked before choosing a migration target:
https://learn.microsoft.com/azure/azure-functions/functions-versions

Changing a template string is insufficient: these templates reference externally hosted
prebuilt ZIPs through `WEBSITE_RUN_FROM_PACKAGE`. Rebuild, inspect, stage and publish the
matching connector package before changing deployment references. Neither cloud resources
nor hosted packages were changed during this review.

## Findings and corrections

### AWS Security Hub — isolated high-risk draft

The original pair `cryptography==50.0.0` / `pyOpenSSL==17.5.0` installed on Python 3.12.14,
but `import OpenSSL` failed with `AttributeError: module 'lib' has no attribute 'GEN_EMAIL'`.
A successful resolver or `pip check` alone would miss this failure.

Additional exact metadata conflicts:

- cryptography 50.0.0 requires cffi >=2.0.0; requirements pin 1.14.6 (introduced by this PR).
- pyasn1-modules 0.2.1 requires pyasn1 >=0.4.1,<0.5.0; PR pins 0.6.4 (introduced by this PR).
- boto3 1.9.180 requires botocore >=1.12.180,<1.13.0; requirements pin 1.12.10 (pre-existing).

The isolated draft corrects these to pyOpenSSL 26.4.0, cffi 2.1.1,
pyasn1-modules 0.4.2 and botocore 1.12.180. The resulting full file resolves for Python 3.11.
pyOpenSSL 26.4.0 explicitly requires cryptography >=49,<51. Its import, TLS context
creation and ASN.1 schema import passed with cryptography 50.0.0 on Python 3.11.17.

**This is only a partial repair:** the now-consistent legacy boto3/botocore pair still fails
on Python 3.11 importing `Mapping` from `collections`. The connector also imports `asn1`,
which is not supplied by `asn1crypto` or `pyasn1`, and retains obsolete native build pins
such as pycrypto 2.6.1 and zope.interface 4.1.1. A supported-runtime migration, SDK upgrade,
requirements cleanup and STS/Security Hub ingestion tests are required before merging.
Do not infer that the full AWS connector installs or runs from the passing crypto probe.

### Other connectors

| Connector | Original Python 3.11 result | Tested correction / remaining gate |
|---|---|---|
| Box | Installs, but JWTAuth import fails: requests-toolbelt 0.10.1 imports removed urllib3 `appengine` | Upgrade Box SDK to 3.14.0 and require requests-toolbelt >=1,<2. Actual JWTAuth generates an RS256 assertion verified with PyJWT 2.15.0 / cryptography 50.0.0. Runtime/package staging still required. |
| Cloudflare | Installs; Azure Blob SDK import fails on missing `six` | Explicit six 1.17.0; SDK import and actual connector HTTP/signature/payload probe pass. |
| CrowdStrike | Resolves; gzip-stream requires a source build | Source installation succeeds; aiobotocore S3 client creation and connector HTTP probe pass. Resolved aiobotocore 3.9.2 / botocore 1.43.106; live SQS/S3 processing remains untested. |
| GCP Monitoring | Installs; old Monitoring SDK imports missing `pkg_resources` | Explicit setuptools 80.9.0 (<81) and six 1.17.0; SDK import and HTTP probe pass. Temporary compatibility bridge; upgrade the Monitoring SDK in a separate migration. |
| Prisma Cloud | Installs; Azure File Share SDK import fails on missing `six` | Explicit six 1.17.0; SDK import and HTTP probe pass. |
| Rapid7 | Installs; HTTP/signature/payload probe passes | Runtime/package staging and actual API pagination/retry validation remain. |
| Snowflake | Installs; SDK import and all four query/row-conversion/close probes pass | Isolated major-version draft. Fake cursors do not validate login, permissions, OCSP/TLS or live query behaviour. |
| Trend Micro (both copies) | Resolves but Python 3.11 full installation fails building orjson 3.7.6 | No silent orjson/pydantic/runtime upgrade. Actual pure JWT helper passes in isolation with PyJWT 2.15.0; complete connector is unvalidated. |

Box's requests-toolbelt/urllib3 and the Azure SDK import failures are existing dependency
closure problems exposed by clean installation, not proven regressions introduced solely
by this PR. Corrections here are tested candidate changes and do not remove the runtime gate.

Snowflake's resolution selected cffi 1.17.1, cryptography 46.0.0 and pyOpenSSL 25.3.0.
It must remain isolated from the AWS crypto constraints: Snowflake 3.18.1 declares cffi <2
and pyOpenSSL <26. Its older resolved crypto stack also needs a separate vulnerability review;
this document does not certify any connector as free of known vulnerabilities.

## Reproduction

Use a separate virtual environment per connector, never one combined requirements environment.
With `uv` installed:

```sh
uv pip compile --python-version 3.8 '<connector>/requirements.txt' -o /tmp/runtime.lock
uv venv --python 3.11 /tmp/connector-check
uv pip install --python /tmp/connector-check/bin/python -r '<connector>/requirements.txt'
uv pip check --python /tmp/connector-check/bin/python
/tmp/connector-check/bin/python .github/dependency-validation/smoke.py <connector-name>
```

Probe names: `box`, `cloudflare`, `crowdstrike`, `gcp`, `prisma`, `rapid7`, `snowflake`, `trend`.
The async probes run a loopback HTTP receiver and check actual emitted JSON, HMAC signature,
headers and success counters. Snowflake uses fake cursors. Box mocks token exchange after
real RSA assertion generation. Trend extracts and executes the two actual pure helpers;
it deliberately does not pretend to load the entire configuration-dependent connector.
No tenant credentials, vendor network calls or Azure ingestion were used.

For the original failing OpenSSL pair, in a disposable Python 3.12 environment:

```sh
python -m pip install cryptography==50.0.0 pyOpenSSL==17.5.0
python -c 'import OpenSSL'
```

## Merge conditions

1. Select a supported Python/Functions runtime and update the full deployment/package path.
2. Install each complete requirements file cleanly on that exact runtime; `pip check` and
   SDK/entry-point imports must pass. Retain the resolved dependency versions as evidence.
3. Run these offline probes plus connector-specific authentication, pagination, retry,
   checkpointing and ingestion tests in staging; compare event counts and payloads with baseline.
4. Resolve AWS legacy SDK/native dependencies and Trend Micro's native/runtime migration.
5. Recheck CI and the precise reviewed head. Merge each independent change only after its gates pass.

## Split pull requests

- AWS partial repair and runtime migration: https://github.com/guden/Azure-Sentinel/pull/16
- Snowflake 3.x migration: https://github.com/guden/Azure-Sentinel/pull/17

Both are drafts. Their requirements changes have been removed from PR #15.

## Second validation pass

Rechecked the published heads, rather than the original working copy:

- PR #15: `16ca800263283d52e83a53dc110342d9e0c63151`
- PR #16: `447d8d7b5b4290ec9352cee2ce11f562a72e6377`
- PR #17: `ed54a46edbf39a26708bde4104f5de46b005afdc`

All remained open, draft and unmerged. Each had a successful `github-advanced-security`
check. Inspection of PR #15's job log shows a security review, not connector execution;
that green check is not evidence of dependency installation or functional compatibility.

On Python 3.11.17, seven connectors each passed (21 checks total):

1. Actual entry-point module import and callable `main`, using synthetic configuration
   with socket connections blocked.
2. The committed offline compatibility probe.
3. Installed dependency consistency (`uv pip check`).

Connectors: Box, Cloudflare, CrowdStrike, GCP Monitoring, Prisma Cloud and Rapid7 from
PR #15, plus Snowflake from PR #17. The isolated environments from the initial clean
install tests were reused; this second pass does not claim a fresh installation.
GCP continues to emit the expected pkg_resources deprecation warning.

`revalidation.json` records the source heads, outputs and all installed package versions.
`entry_import.py` contains the added import probe; run it in a connector-specific environment:

```sh
python .github/dependency-validation/entry_import.py . \
  'Solutions/Box/Data Connectors/AzureFunctionBox' main.py
```

Also confirmed that AWS and Snowflake requirements in PR #15 exactly match the base
commit after the split. The smoke script in PR #17 is identical to PR #15's version.
No deployment files or production connector code were changed in this second pass.
The runtime, AWS, Trend Micro and live-staging blockers above remain unresolved;
these results do not authorise a merge.
