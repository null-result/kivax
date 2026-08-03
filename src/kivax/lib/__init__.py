"""The library modules behind the CLI's subcommands.

Each `kivax_<name>.py` here is both an importable module and a script: the
ones backing `kivax validate|hash|trace|state|task|wiki|lessons|specfirst`
have a `main()` and a `__main__` guard, and the CLI dispatches to them with
`python -m kivax.lib.kivax_<name>`.
"""
