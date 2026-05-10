"""jtl2datev CLI package.

Definiert die Click-Group `main` und registriert alle Sub-Commands.
Sub-Commands liegen in eigenen Modulen und registrieren sich via
`@main.command(...)`-Decorators beim Import unten.
"""
import logging

import click


@click.group()
@click.option(
    "-v", "--verbose",
    is_flag=True,
    default=False,
    help="Detailliertes Logging (INFO-Level). Default: nur ERROR + Warnungen.",
)
@click.pass_context
def main(ctx: click.Context, verbose: bool) -> None:
    """jtl2datev — JTL-Rechnungen ins DATEV-Format exportieren."""
    if verbose:
        logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
    else:
        # Standard: nur ERROR ins Terminal. Bibliotheks-WARNINGs (z.B. "Unknown
        # platform 'Weitere Verkaufskanäle'") werden unterdrückt — Fallback auf
        # DE-Marketplace ist im Code dokumentiert und im Routinebetrieb nicht
        # handlungsrelevant.
        logging.basicConfig(level=logging.ERROR, format="%(levelname)s: %(message)s")
    ctx.obj = {"verbose": verbose}


@main.command()
def version() -> None:
    from jtl2datev import __version__

    click.echo(__version__)


# Sub-Command-Registrierung via Side-Effect-Imports. Reihenfolge irrelevant.
from jtl2datev.cli import (  # noqa: E402, F401  (registration side-effects)
    export_datev,
    export_dutypay,
    export_taxually,
    export_verbringung,
    import_rates,
    mixed_vat_check,
    reconcile,
)


if __name__ == "__main__":
    main()
