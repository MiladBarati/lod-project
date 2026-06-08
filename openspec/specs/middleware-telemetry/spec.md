# middleware-telemetry Specification

## Purpose
TBD - created by archiving change add-middleware-telemetry. Update Purpose after archive.
## Requirements
### Requirement: Telemetry Initialization
The LOD middleware adapters and transports SHALL accept a telemetry configuration dictionary or object containing `telemetry_endpoint` (string URL), `telemetry_api_key` (optional string), and `enabled` (boolean, defaulting to True).

#### Scenario: Telemetry initialized with configuration
- **WHEN** the `LODRequestsAdapter` or `LODHTTPXTransport` is initialized with configuration `telemetry_endpoint="https://telemetry.lod.sh/v1"`, `telemetry_api_key="lod_test_key"`, and `enabled=True`
- **THEN** the telemetry reporter is active and configured to use the specified endpoint and credentials

---

### Requirement: Telemetry Payload Privacy Masking
The telemetry reporter MUST NOT send raw HTTP request bodies, authorization headers, or sensitive query parameter values. It SHALL restrict the telemetry payload to structural metadata: HTTP method, URL path (with query parameter values redacted), schema validation error path/location, schema violation type, error message, client/agent identifier, and timestamp.

#### Scenario: Reporting validation failure with masked data
- **WHEN** a request fails body schema validation (e.g. missing required field 'email')
- **THEN** the dispatched telemetry payload includes the error location "body", parameter "email", issue "missing_required_parameter", and the URL path "/users", but does not include any part of the request body content or authentication headers

---

### Requirement: Asynchronous Non-Blocking Dispatching
The telemetry reporter SHALL enqueue telemetry events to an in-memory queue and dispatch them to the telemetry endpoint using a background worker thread or asynchronous task, ensuring zero blocking latency is added to the primary HTTP request execution path.

#### Scenario: Telemetry reporting executes asynchronously
- **WHEN** validation fails on an outgoing request and telemetry is triggered
- **THEN** the event is queued and the main request adapter/transport returns immediately without waiting for the telemetry HTTP POST request to complete

---

### Requirement: Graceful Failure Handling
The telemetry reporter SHALL handle its own network or server errors gracefully. If the telemetry endpoint returns a non-2xx response or is unreachable, the reporter MUST log a warning message and must not raise any exceptions to the parent application.

#### Scenario: Telemetry endpoint is offline
- **WHEN** the telemetry HTTP POST request fails due to a network connection timeout
- **THEN** a warning is logged to standard logger and the parent application continues execution without raising an exception

