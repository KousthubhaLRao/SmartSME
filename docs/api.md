# HTTP API

Every endpoint, and the conventions they share.

[&larr; Back to the README](../README.md)

---

## API reference

Interactive docs at **<http://localhost:8000/docs>**. Summary:

| Area | Endpoints |
|---|---|
| Meta | `GET /api/health` (public) |
| Auth | `POST /api/auth/sign-in` · `sign-up` · `sign-out` · `GET /api/auth/me` |
| Dashboard | `GET /api/dashboard` |
| Sales | `GET/POST /api/sales` · `GET /api/sales/{id}` · `POST {id}/payment` · `{id}/cancel` · `PATCH {id}/date` |
| Purchases | same shape under `/api/purchases` |
| Products | `GET/POST /api/products` · `PUT/DELETE {id}` · `POST {id}/adjust` |
| Parties | `GET/POST /api/parties` · `PUT/DELETE {id}` · `POST {id}/settle` · `POST /settle-all/{kind}` |
| Expenses | `GET/POST /api/expenses` · `DELETE {id}` |
| Smart Input | `GET /api/input/status` · `POST /parse-text` · `/parse-image` · `/publish` |
| Reports | `GET /api/reports/overview` · `/revenue` · `/preview` · `/download` |
| Workflow | `GET /api/workflow` · `POST /rules` · `PUT/DELETE /rules/{id}` · `POST /rules/{id}/toggle` |
| Events | `GET /api/events` · `POST /events/{id}/replay` · `POST /events/drain` |
| Notifications | `GET /api/notifications` · `/unread-count` · `POST {id}/read` · `/read-all` |
| Settings | `GET/PUT /api/settings` |

Requests use camelCase JSON to match the React code; the database stays
snake_case. Domain validation errors come back as `400 {"detail": "..."}`.

---

