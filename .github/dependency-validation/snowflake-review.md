# Snowflake connector 3.x migration (split from PR #15)

Draft; do not merge until runtime/package and staging checks pass.

Isolates snowflake-connector-python 2.8.3 -> 3.18.1 from the unrelated connectors.
The deployment template still uses Python 3.8, whereas 3.18.1 requires Python >=3.9.

Validated 22 October 2026 on Python 3.11.17: full requirements resolve and install;
SDK import succeeds; offline probes exercise all four connector query paths with fake
DictCursor responses, timestamp serialisation and cursor cleanup. They do NOT validate
real authentication, account permissions, OCSP/TLS or live Snowflake ingestion.

Resolved crypto dependencies include cffi 1.17.1, cryptography 46.0.0 and pyOpenSSL 25.3.0.
Snowflake 3.18.1 requires cffi <2 and pyOpenSSL <26; do not combine its environment with
AWS's cryptography 50 / pyOpenSSL 26 constraints. Review the resolved stack for security
advisories separately before approval.

Before merging: choose a supported Functions/Python runtime, rebuild and stage the ZIP
referenced by WEBSITE_RUN_FROM_PACKAGE, and verify login/query history, reader-account
queries, authentication, checkpointing and Sentinel ingestion against the baseline.

Reproduction after installing this connector's requirements into a separate Python 3.11
virtual environment:

    python .github/dependency-validation/smoke.py snowflake

The probe uses only local fake credentials and mocked query responses; it makes no vendor calls.
