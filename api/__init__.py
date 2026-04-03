"""
API package — clean architecture FastAPI backend.

Layers:
  api/
    models/     – Pydantic request/response schemas
    services/   – Business logic (auth, products, prices, sellers)
    routers/    – Thin FastAPI route handlers
    deps.py     – FastAPI dependency injection (DB, cache, current user)
    cache.py    – Redis cache wrapper
    auth.py     – JWT creation + verification
    logging_cfg.py – Structured logging setup
    main.py     – App factory (replaces fastapi_app.py)
"""
