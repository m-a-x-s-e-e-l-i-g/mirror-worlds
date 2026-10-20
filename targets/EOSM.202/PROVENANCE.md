# Exact installed-build export table

`EOSM_202.sym` is copied byte-for-byte from `ML/modules/EOSM_202.sym` in
the official [2025-06-20 EOS M dev archive](https://builds.magiclantern.fm/builds/dev/magiclantern.2025-06-20.EOSM.202.zip).

- Archive SHA-256, verified after download on 2026-10-19:
  `152f2ab46b83f45b978bcb704bda976849aa9d06b08fb70448f69be3ebfc44fb`
- Symbol table SHA-256:
  `d9ac74b62303e149ccf9b636e9dfd5fb24bc26506660b4b0638acbb51715fb88`
- Target Canon firmware: EOS M 2.0.2.
- Official source revision: `ed3e7c0dfacfdeaf3349dee73edf9e3621217462`.
- Source project/license: Magic Lantern, GPL; this is generated export metadata,
  retained without changing addresses or names.

This table allows offline module-import checks against the actual distribution,
without distributing a rebuilt or replacement core. A successful name/ABI audit
does not establish that a module has loaded or run on a physical camera.
