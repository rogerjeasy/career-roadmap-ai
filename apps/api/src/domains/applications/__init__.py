"""Job Applications domain (§10.2) — CV rewrite + cover letter + tracking.

Completes the flagship application flow that the parse-only ``cv`` domain leaves
open. A user tracks each role they're pursuing through a status pipeline
(saved → applied → interviewing → offer → closed), and for any application can
generate, grounded in their REAL CV text (stored in the session by the cv domain)
plus their Evidence Vault:
  • a tailored CV rewrite — sharpened summary, rewritten bullets, and the
    job-description keywords they match vs. the ones they're missing;
  • a tailored cover letter.

The LLM only rewrites what the user actually has — it never invents employers,
titles, or metrics — and never infers protected attributes.
"""
