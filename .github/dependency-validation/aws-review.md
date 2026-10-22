# AWS dependency migration (split from PR #15)

Draft; not safe to merge. Original source: 0e640b274ed6d3ef2fe1c689820275b3fb3cbb41.

Retains the proposed aiohttp, cryptography and pyasn1 upgrades, while correcting:
- pyOpenSSL 17.5.0 -> 26.4.0 (supports cryptography >=49,<51)
- cffi 1.14.6 -> 2.1.1 (cryptography 50 requires >=2)
- pyasn1-modules 0.2.1 -> 0.4.2 (supports pyasn1 0.6.4)
- botocore 1.12.10 -> 1.12.180 (matches boto3 1.9.180)

Validation on 22 October 2026: complete corrected requirements resolve on Python 3.11.17.
The isolated crypto/ASN.1 subset installs, imports and creates an OpenSSL TLS client context.
The original OpenSSL pair installs on Python 3.12.14 but crashes on import (missing GEN_EMAIL).

Remaining blockers: the legacy boto3/botocore pair fails on Python 3.11 importing Mapping
from collections; the deployment still specifies Python 3.8 / Functions ~3; the code imports
asn1 without a matching dependency and retains obsolete native build pins (pycrypto,
zope.interface). Full installation and real connector functionality have NOT been validated.

Before merging, migrate the AWS SDK and runtime together, clean up unused legacy imports
and dependencies, rebuild the actual deployment ZIP, and test STS web-identity authentication,
Security Hub pagination/filtering, timestamp handling and Sentinel ingestion in staging.
Do not merge this partial repair on the strength of the crypto-only probe.

Full cross-connector review and reproducible offline probes are in PR #15 under
.github/dependency-validation/README.md and smoke.py.
