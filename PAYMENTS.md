# Quantum Payments & Credits

Shared prepaid-credit contract for Quantum AI projects.

- Credits are granted only after a verified, idempotent payment event.
- Use provider adapters/webhooks for Stripe or crypto payments.
- Never store crypto private keys or custody funds here.
- Production balances and ledger entries must be transactional and persistent (PostgreSQL recommended).
- Generation work should reserve credits before execution and release them on failure.
- Secrets belong in deployment secret storage, never in Git.
