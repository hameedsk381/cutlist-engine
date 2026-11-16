"""SaaS control plane: users, projects, and async jobs around the engine.

Layered on top of the core engine (parsers -> pipeline -> outputs). The engine
library is untouched; the SaaS layer adds multi-tenancy, auth, a DB-backed
job queue and per-project artifact storage.
"""
