# Live execution halt — 2026-09-22

At 17:48 UTC, the shared state machine entered `halted` after the paper COP
protective stop failed. The broad live worker subsequently exited with
`state_is_not_live`; it did not continue scanning. This shows a cross-mode
failure: a paper safety event stopped the live worker.

The live ORCL position remained open after its fractional DAY stop expired at
the regular-market close. Read-only checks found 0.223500044 ORCL shares and
no active sell order. The available broker quote was over two hours old, so
there was no reliable price for a bounded after-hours limit sell.

Under the user's standing authorization for emergency exits after protective
stop failure, a sell-only, exact-quantity DAY market order was submitted by
the guarded emergency path. Alpaca accepted order
`773eee6e-c49f-4ce1-a2cd-f1920c302256` for 0.223500044 ORCL shares;
immediate verification showed `filled_qty=0` and the position still open.
The order is pending, not a completed exit. The live state remains halted.

Before resuming automated entries, verify the broker fill, reconcile the live
trade ledger and risk reservation, and separate paper and live kill-switch
state so a paper stop failure cannot silently stop live position management.
Future fractional DAY-stop entries also need a tested end-of-session exit plan.
