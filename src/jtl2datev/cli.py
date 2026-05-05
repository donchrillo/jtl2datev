import click


@click.group()
def main() -> None:
    """jtl2datev — JTL-Rechnungen ins DATEV-Format exportieren."""


@main.command()
def version() -> None:
    from jtl2datev import __version__

    click.echo(__version__)


if __name__ == "__main__":
    main()
