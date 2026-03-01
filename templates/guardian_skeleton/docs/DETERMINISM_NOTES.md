# Determinism Notes

This document records assumptions and requirements for deterministic behavior across guardians:

- All outputs must be reproducible given the same inputs.
- Sorting keys and canonical JSON serialization is enforced for all example outputs.
- No network calls are performed during checks.
- Any drift from deterministic outputs must be explicitly documented here.