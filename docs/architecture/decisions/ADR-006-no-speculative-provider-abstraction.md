# ADR-006: No Speculative Bank-Provider Abstraction

## Context

Plaid is the only current bank aggregator. Other providers are not confirmed roadmap requirements.

## Decision

Do not create an `IBankProvider`, provider registry, or generic bank-sync framework solely for hypothetical MX/Teller/Finicity support.

## Consequences

Keep Plaid integrations concrete. Revisit only when a second provider or confirmed near-term provider requirement exists.
