# Queue Backends

Calseta AI uses an abstract task queue interface (`TaskQueueBase`) backed by
procrastinate + PostgreSQL by default.

## Switching Backends

Set the `QUEUE_BACKEND` environment variable:

| Value | Backend | Status |
|---|---|---|
| `postgres` | procrastinate + PostgreSQL | ✅ Implemented (default) |
| `celery_redis` | Celery + Redis | 🚧 Stub — not implemented |
| `sqs` | AWS SQS | 🚧 Stub — not implemented |
| `azure_service_bus` | Azure Service Bus | 🚧 Stub — not implemented |

## Implementing an Alternative Backend

TODO: Document the steps to implement a new `TaskQueueBase` subclass
and wire it into `app/queue/factory.py`.
