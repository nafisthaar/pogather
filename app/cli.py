import click
from flask import current_app

from . import demo
from .db import connect
from .errors import AppError
from .services import auth_service


def register(app):
    @app.cli.command("create-owner")
    @click.option("--username", prompt=True)
    @click.option("--full-name", prompt=True)
    @click.password_option()
    def create_owner(username, full_name, password):
        """Create a seller (owner) login. The password is asked with hidden input unless given."""
        conn = connect(current_app.config["DATABASE"])
        try:
            auth_service.create_owner(conn, username, password, full_name)
        except AppError as error:
            raise click.ClickException(str(error)) from None
        finally:
            conn.close()
        click.echo(f"Created owner '{username}'.")

    @app.cli.command("seed-demo")
    @click.option("--owner-password", required=True)
    @click.option("--customer-password", required=True)
    def seed_demo(owner_password, customer_password):
        """Add the demo accounts, menu and two POs. Run it on an empty database."""
        conn = connect(current_app.config["DATABASE"])
        try:
            demo.seed(conn, owner_password, customer_password)
        except AppError as error:
            raise click.ClickException(
                f"Could not seed the demo data: {error} Run it on an empty database "
                "(delete instance/pogather.sqlite3 to start over)."
            ) from None
        finally:
            conn.close()
        click.echo("Demo data added.")
