# Security Notice

Bu sürüm **tek kullanıcılı yerel kullanım** içindir.

İnternete açık veya çok kullanıcılı üretim ortamında aşağıdakiler tamamlanmadan kullanılmamalıdır:

- JWT/session authentication
- Tenant izolasyonu
- Case ownership (actor-based access control)
- PostgreSQL kalıcılığı
- Soft delete ve retention policy
- Backend export güvenliği
- Rate limiting (production-grade, Redis-based)
- HTTPS/TLS enforcement
