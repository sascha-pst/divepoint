# Divepoint
Read the PRD in docs before changing product behavior. Build data-first in milestone order.
- Only occurrence retrieval code may add species to a manifest; never the LLM.
- Key species by accepted WoRMS AphiaID. Require qualifying area evidence.
- Tests and quick evals must run offline. Synthetic fixtures are not scientific evidence.
- Photos require an allowed licence, attribution, and source URL.
- Run `uv run --project backend pytest backend/tests` and `uv run --project backend python evals/run_evals.py --quick`.
