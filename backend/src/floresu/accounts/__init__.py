"""Human accounts: email/password registration, login, and signed sessions.

The internet-facing half of Floresu's two auth systems (the other is agent OAuth).
Accounts are email plus a bcrypt-hashed password; a signed HS256 access/refresh
cookie pair carries the human session. Business rules live in
:class:`~floresu.accounts.service.AccountService`; the two thin routers
(``/auth/*`` and ``GET /me``) are mounted on the external app only.
"""

from __future__ import annotations
