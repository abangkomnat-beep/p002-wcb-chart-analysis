# BTCUSD F+ contract fixtures

Fixtures in this directory are synthetic and offline-only. They define the public
contract between Tester and Builder; they are not market recommendations and must
never be copied to production Output or publishing paths.

`runtime_shadow_inputs.json` supplies deterministic candidate inputs and narratives for
the synthetic Shadow S01 contract. It never calls WCB/network and must never write final
Output or the production daily lock.
