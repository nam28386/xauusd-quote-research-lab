# Repository instructions

- Use Python 3.12. Read `README.md` and `docs/CODEX_NEW_CHAT_MASTER.md` in full before implementing research code. Resolve any missing canonical specification with its owner.
- Use synthetic inputs in Codex Cloud. Keep credentials, account information, private or real broker quotes, trading interfaces, broker connections, and terminal integrations out of the repository and cloud workflow.
- Treat raw quote observations as immutable. Keep source and receive timestamps distinct, preserve provenance and quality decisions, and retain REAL and DEMO as distinct labels in synthetic scenarios.
- Enforce no-lookahead at every evaluation timestamp. Use only observations received by that time. Preserve gaps and exclusions. An invalid latest observation must block that match. Repeated polling snapshots are observations and do not establish new market ticks.
- Use `Decimal` for quote prices and derived price measures. Version domain contracts and evidence packets explicitly. Record assumptions, provenance, and epistemic status alongside research outputs.
- Limit conclusions to what quoted bid and ask observations support. They cannot establish broker intent, dealer inventory, routing, executable arbitrage, or realized trading costs.
