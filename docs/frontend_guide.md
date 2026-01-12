# Frontend Integration Guide

This backend provides a unified `/chat` API for the Facility Operations Assistant.

## API Contracts

### 1. Start Session
**POST** `/session/start`
- **Response**: `{ "session_id": "uuid", "message": "Session started" }`
- **Usage**: Call this on app load or new conversation.

### 2. Send Message (Chat/SQL/Workflow)
**POST** `/chat`
- **Headers**:
    - `X-Trace-Id`: (Optional) UUID for traversing logs.
- **Body**:
```json
{
  "session_id": "uuid from start",
  "message": "User input text",
  "mode": "chat", // Optional hint: chat, sql, workflow
  "metadata": {
    "timezone": "UTC"
  }
}
```

### 3. Handle Response
The response is polymorphic.
**Response**:
```json
{
  "session_id": "uuid",
  "message": "Assistant text response",
  "status": "ok",
  "labels": ["intent_label"],
  "workflow": { ... },
  "sql": {
    "ran": true,
    "rows_preview": { ... TOON Encoded Object ... } 
  },
  "toon": {
    "raw_tokens": 1000,
    "toon_tokens": 300,
    "reduction_pct": 70.0
  }
}
```

## 🔹 TOON Decoding (Important)
The backend now uses **TOON (Token-Oriented Object Notation)** to compress SQL results. The `sql.rows_preview` field will return a compressed object structure.

**Structure:**
```json
{
  "data": { ... structure with references ~1, ~2 ... },
  "lookup": [ "string1", "string2", ... ]
}
```

**Decoding Algorithm:**
To display the data, your frontend must "hydrate" the references.
1.  Recursively traverse the `data` object.
2.  If you encounter a string starting with `~` (tilde) followed by a number (e.g., `~5`):
    - Parse the index (5).
    - Replace the string with `lookup[5]`.
3.  If a string starts with `~~`, it is an escaped tilde. Replace with `~`.

## UI State Management

1.  **Chat Mode**: Standard message display.
2.  **Workflow Mode**:
    - Render interactive elements based on `workflow.view.type` (menu, input, confirmation).
    - Send user interactions back to `/chat`.
3.  **SQL Mode**:
    - **Decode** `sql.rows_preview` using the TOON logic above.
    - Display the decoded data in a table/grid.
    - Show the `toon.reduction_pct` as a "Network Savings" badge.

## Error Handling
- Check `status` field. If `error`, display `message` as an alert.
