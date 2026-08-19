"""GovAssist Phase 2 -- the service that serves what the corpus builds.

Never reads scheme.md. Never re-derives a fact the corpus toolchain already
validated. Reads only data/schemes/*/build/*.json, which is generated,
checksummed-in-spirit by validate.py, and committed.
"""
