"""P1.4.1 — Repository base and dual-write support.

Note: BaseRepository, SoftDeleteQueryBuilder, OptimisticLock, and TransactionContext
were removed during P1 foundation audit. The production repository implementations
(JobRepository, UserRepository, AuthSessionRepository, CaseMemberRepository)
are standalone classes that do not extend a shared base. Dual-write and
optimistic concurrency patterns can be reintroduced in P1.9+ as needed.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)
