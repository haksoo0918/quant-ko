# Backend & API Architecture Standards

This document establishes server-side development practices, RESTful/GraphQL API design principles, and database handling guidelines.

## 1. API Design & Resource Modeling

1. **RESTful Resource Naming**:
   - Use plural nouns for resource endpoints: `/api/v1/users`, `/api/v1/projects/:id/tasks`.
   - Use standard HTTP verbs properly: `GET` (read), `POST` (create), `PUT`/`PATCH` (update), `DELETE` (remove).
2. **Predictable Response Envelope**:
   - Return consistent JSON structures for both success and error responses:
   ```json
   {
     "success": true,
     "data": { ... },
     "error": null,
     "meta": { "page": 1, "total": 42 }
   }
   ```
3. **HTTP Status Codes**:
   - `200 OK` / `201 Created` / `204 No Content`
   - `400 Bad Request` (validation errors)
   - `401 Unauthorized` / `403 Forbidden`
   - `404 Not Found`
   - `422 Unprocessable Entity`
   - `500 Internal Server Error`

---

## 2. Input Validation & Defensive Engineering

1. **Strict Input Schema Validation**:
   - Validate every inbound payload using schema libraries (e.g. Zod, Pydantic, class-validator) before processing.
   - Reject unexpected or extraneous parameters.
2. **Authentication & Authorization**:
   - Verify identity and permissions at the route or controller level before executing business logic.
   - Prevent Indirect Object Reference (IDOR) by verifying ownership against the authenticated session.

---

## 3. Error Handling & Structured Logging

1. **No Silent Failures**: Always handle and catch exceptions explicitly. Return user-friendly error messages without leaking stack traces or internal environment details.
2. **Structured Logging**:
   - Emit machine-readable logs (JSON format) with timestamp, log level, correlation/request ID, endpoint, and error context.
   - Never log sensitive credentials, passwords, or personal identifiable information (PII).

---

## 4. Database Operations & Data Integrity

1. **Transactions for Multi-Step Mutations**: Wrap multi-entity updates in atomic database transactions (`BEGIN ... COMMIT`).
2. **Migrations Over Ad-hoc Alterations**:
   - All schema alterations must be committed as code via migration files.
   - Ensure backward compatibility when adding columns or altering types.
