# workflow/

Scripts in this folder are designed to be run by Snakemake only.
They use the `snakemake` object which is injected automatically at runtime.

Running these scripts directly will raise a `RuntimeError`.

See the `Snakefile` for how each script is called.