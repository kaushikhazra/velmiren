"""
Velmiren CLI — Click command surface.
"""

from __future__ import annotations

import sys

import click

from velmiren import auth, drive, paths
from velmiren.errors import (
    EXIT_NOT_FOUND,
    NotAuthenticatedError,
    RemoteNotFoundError,
    UserError,
    VelmirenError,
)


# ---------------------------------------------------------------------------
# Error handler
# ---------------------------------------------------------------------------


def _run(fn, *args, **kwargs):
    """Wrap a command body; catch VelmirenError and exit cleanly."""
    try:
        fn(*args, **kwargs)
    except VelmirenError as exc:
        click.echo(exc.message, err=True)
        sys.exit(exc.exit_code)


# ---------------------------------------------------------------------------
# CLI group
# ---------------------------------------------------------------------------


@click.group()
def main():
    """Velmiren — file transport to/from Google Drive."""


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@main.command("auth")
@click.argument("provider", default="google")
def auth_google(provider: str):
    """Authenticate with Google Drive (OAuth2)."""
    def _body():
        if provider != "google":
            raise UserError(f"unsupported provider: {provider}")
        client_id, client_secret = auth._get_client_config()
        cred_data = auth.run_oauth_flow(client_id, client_secret)
        auth._atomic_write_cred(cred_data)
        email = cred_data.get("email", "")
        click.echo(f"OK — authenticated as {email}")

    _run(_body)


@main.command("status")
def status():
    """Show authentication state and account info."""
    def _body():
        info = auth.get_status()
        cred_path = info.get("cred_path", "")
        if not info["authenticated"]:
            click.echo("Auth state: not authenticated")
            click.echo(f"Cred file: {cred_path}")
            raise NotAuthenticatedError()
        # Load cred to get token expiry (triggers refresh as side effect)
        cred = auth.load()
        expiry = ""
        if hasattr(cred, "expiry") and cred.expiry:
            expiry = cred.expiry.isoformat() + "Z" if not str(cred.expiry).endswith("Z") else str(cred.expiry)
        click.echo("Auth state: authenticated")
        click.echo(f"Account: {info.get('email', '')}")
        click.echo(f"Token expiry: {expiry}")
        click.echo(f"Cred file: {cred_path}")

    _run(_body)


@main.command("send")
@click.argument("local_path")
@click.option("--to", "remote_path", required=True, help="Remote Drive path")
@click.option("--quiet", "-q", is_flag=True, help="Suppress upload progress")
def send(local_path: str, remote_path: str, quiet: bool):
    """Upload a local file to Drive (resumable, supports multi-GB)."""
    def _body():
        cred = auth.load()

        def _progress(uploaded: int, total: int):
            pct = (uploaded / total * 100) if total else 0
            click.echo(f"\r  {pct:5.1f}%  {uploaded:>14,} / {total:,} bytes", nl=False, err=True)

        cb = None if quiet else _progress
        file_id = drive.upload(cred, local_path, remote_path, progress=cb)
        if not quiet:
            click.echo("", err=True)  # newline after final progress line
        click.echo(f"{file_id}  {remote_path}")

    _run(_body)


@main.command("fetch")
@click.argument("remote_path")
@click.option("--to", "local_path", required=True, help="Local destination path or directory")
def fetch(remote_path: str, local_path: str):
    """Download a remote Drive file to local disk."""
    def _body():
        cred = auth.load()
        bytes_written = drive.download(cred, remote_path, local_path)
        click.echo(f"{local_path}  {bytes_written} bytes")

    _run(_body)


@main.command("list")
@click.argument("remote_dir", required=False, default=None)
def list_files(remote_dir: str | None):
    """List files in a remote Drive directory."""
    def _body():
        cred = auth.load()
        svc = drive._service(cred)

        if remote_dir:
            try:
                folder_id = paths.resolve(svc, remote_dir)
            except RemoteNotFoundError:
                raise RemoteNotFoundError("no such remote folder")
        else:
            # List the configured remote root via the public helper
            folder_id = paths.resolve_root_id(svc)

        files = drive.list_dir(cred, folder_id)
        for f in files:
            name = f.get("name", "")
            size = f.get("size", "0")
            modified = f.get("modifiedTime", "")
            fid = f.get("id", "")
            click.echo(f"{name}  {size}  {modified}  {fid}")

    _run(_body)


@main.command("exists")
@click.argument("remote_path")
def exists(remote_path: str):
    """Check whether a remote file exists. Exits 0 if true, 1 if false."""
    def _body():
        cred = auth.load()
        found = drive.file_exists(cred, remote_path)
        click.echo("true" if found else "false")
        if not found:
            sys.exit(EXIT_NOT_FOUND)

    _run(_body)


@main.command("delete")
@click.argument("remote_path")
@click.option("--force", is_flag=True, default=False, help="Required to confirm deletion")
def delete(remote_path: str, force: bool):
    """Delete a remote Drive file. Requires --force."""
    def _body():
        if not force:
            raise UserError("--force required")
        cred = auth.load()
        drive.delete_file(cred, remote_path)

    _run(_body)
