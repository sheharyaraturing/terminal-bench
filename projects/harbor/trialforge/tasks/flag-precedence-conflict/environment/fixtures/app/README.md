# monolith services

    services/checkout        cart, express lane, pricing, session
    services/payments        ledger, settlement, tokenization, gateway
    services/billing         invoices, proration, dunning
    services/notifications   digest, push, templates
    services/search          query parsing, ranking, indexing
    services/reporting       exports, warehouse reads
    services/identity        mfa, sessions, passkeys
    services/ingest          batching, dead-letter replay
    platform/                flag accessors, shadowing, circuit breaker, shared helpers
    web/src/                 the browser bundle
    tests/                   unit tests

Runtime configuration, including every feature gate, is resolved out of
`/data/flags`. See the README there for the layer order. `build-manifest.json`
is the release inventory for production-shipping source; tests and historical
documents are not part of the deployed application.
