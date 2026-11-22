# Task Handler Registry

A deterministic registry for task handlers consumed by later execution adapters.

## API
- `register(name, handler, version="1", input_validator=None)`: register a callable once.
- `resolve(name, version=None)`: resolve a handler and optional exact version.
- `validate_input(name, payload, version=None)`: apply an optional validator.
- `list_handlers()`: return sorted metadata only (never handler objects).
- `unregister(name, version=None)`: remove an exact current registration.

## Guarantees
- Names are constrained to lowercase identifiers with dot/dash/underscore separators.
- Versions are explicit strings and can be pinned during resolution.
- Duplicate registrations fail rather than silently replace handlers.
- Validators must return exactly `True`; falsey values and exceptions fail closed.
- Listing metadata does not expose callable objects.

## Boundaries
The registry does not execute handlers, schedule work, persist registrations, or manage leases.
Execution adapters should resolve by name/version and validate payloads before invocation.
