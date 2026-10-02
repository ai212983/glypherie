# Plans

## TODO

- [ ] **Spacing and kerning:** test Skrifa hinted advances plus HarfRust positioning adjustments in a shared Rust layout
      policy. Review word/pair comparisons across configured families and sizes. Keep Reference output unchanged; assess
      custom optical kerning afterward.

      Problem: Roboto 14 px 1-bit “minimum” has 1 blank column before each i and 3 after it in both
      Reference and `001.01`. A read-only hinted-advance simulation gives uniform 2-column gaps;
      rendered validation remains pending.
