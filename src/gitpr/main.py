# src/gitpr/main.py
import typer
import json
import re
import requests
import os
import platform
import stat
from pathlib import Path
from typing import Optional
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.syntax import Syntax
from git import Repo, InvalidGitRepositoryError
import git.exc
from cryptography.fernet import Fernet
from gitpr.forges import GitHubForge, GitLabForge, Forge

# SETUP
app = typer.Typer(help="The Universal Git CLI Tool")
console = Console()
APP_NAME = "gitpr"
CONFIG_PATH = Path(typer.get_app_dir(APP_NAME)) / "config.json"
KEY_PATH = Path(typer.get_app_dir(APP_NAME)) / ".key"

# SECURITY UTILS
def load_or_create_key():
    if not KEY_PATH.exists():
        if not KEY_PATH.parent.exists(): KEY_PATH.parent.mkdir(parents=True)
        key = Fernet.generate_key()
        with open(KEY_PATH, "wb") as f: f.write(key)
        
        # --- SECURITY FIX: Windows / Unix Permissions ---
        if platform.system() != "Windows":
            try: KEY_PATH.chmod(0o600)
            except: pass
        else:
            try: os.chmod(KEY_PATH, stat.S_IREAD)
            except: pass
            
    with open(KEY_PATH, "rb") as f: return f.read()

def encrypt_token(token: str) -> str:
    f = Fernet(load_or_create_key())
    return f.encrypt(token.encode()).decode()

def decrypt_token(encrypted_token: str) -> str:
    f = Fernet(load_or_create_key())
    return f.decrypt(encrypted_token.encode()).decode()

def load_config():
    if not CONFIG_PATH.exists():
        console.print("[bold red]Not logged in.[/bold red]")
        raise typer.Exit(code=1)
    with open(CONFIG_PATH, "r") as f: return json.load(f)

# FACTORY
def get_forge(repo_context: str) -> Forge:
    if not repo_context:
        console.print("[red]Could not detect git repository context. Are you in a git folder?[/red]")
        raise typer.Exit(1)

    config = load_config()
    repo = Repo(".", search_parent_directories=True)
    remote_url = repo.remotes.origin.url
    
    provider = "github"
    if "gitlab" in remote_url:
        provider = "gitlab"
    
    if provider not in config:
        console.print(f"[red]No config for {provider}. Run `gitpr login --provider {provider}`[/red]")
        raise typer.Exit(1)
        
    prov_conf = config[provider]
    try:
        token = decrypt_token(prov_conf["token"])
    except:
        console.print("[red]Token decrypt failed. Re-login.[/red]")
        raise typer.Exit(1)
        
    if provider == "github":
        return GitHubForge(token, prov_conf["base_url"], repo_context)
    else:
        return GitLabForge(token, prov_conf["base_url"], repo_context)

def get_current_repo_context():
    try:
        repo = Repo(".", search_parent_directories=True)
        remote_url = repo.remotes.origin.url
        match = re.search(r"[:/]([\w-]+)/([\w-]+)(?:\.git)?$", remote_url)
        if match: return f"{match.group(1)}/{match.group(2)}"
        return None
    except: return None

# COMMANDS
@app.command()
def login(
    provider: str = typer.Option("github", "--provider", "-p", help="github or gitlab")
):
    """Login to GitHub or GitLab (Supports Enterprise)."""
    console.rule(f"[bold blue]Setup {provider.upper()}[/bold blue]")
    
    # Provider Setup
    base_url = "https://api.github.com" if provider == "github" else "https://gitlab.com"
    if typer.confirm("Is this an Enterprise instance?", default=False):
        domain = typer.prompt("Enter Domain (e.g. gitlab.company.com)")
        base_url = f"https://{domain}/api/v3" if provider == "github" else f"https://{domain}"

    token = typer.prompt(f"Paste {provider.title()} Token", hide_input=True)
    encrypted_token = encrypt_token(token)

    # Load existing config
    config = {}
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r") as f: config = json.load(f)

    # Save Provider Config
    config[provider] = {"token": encrypted_token, "base_url": base_url}
    
    # Slack Setup (Global)
    configure_slack = True
    if "slack_webhook" in config:
        configure_slack = typer.confirm("Slack is already configured. Update it?", default=False)
    elif typer.confirm("Configure Slack notifications?", default=False):
        pass
    else:
        configure_slack = False

    if configure_slack:
        webhook = typer.prompt("Paste Slack Webhook URL")
        config["slack_webhook"] = webhook
        console.print("[green]✔ Slack configuration updated.[/green]")
    
    # Save Config
    if not CONFIG_PATH.parent.exists(): CONFIG_PATH.parent.mkdir(parents=True)
    with open(CONFIG_PATH, "w") as f: json.dump(config, f)
    
    if platform.system() != "Windows":
        try: CONFIG_PATH.chmod(0o600)
        except: pass
        
    console.print(f"[green]✔ {provider.title()} configuration saved.[/green]")

@app.command()
def create(
    from_branch: str = typer.Option(..., "--from", "-f"),
    to_branch: str = typer.Option(..., "--to", "-t"),
    draft: bool = typer.Option(False, "--draft"),
    repo_context: str = typer.Argument(None, help="Optional: org/repo override")
):
    """Create a PR/MR."""
    ctx = repo_context or get_current_repo_context()
    forge = get_forge(ctx)
    config = load_config()
    
    console.rule(f"[bold blue]Creating Request: {ctx}[/bold blue]")
    title = typer.prompt("Title")
    body = typer.edit(extension=".md")
    
    with console.status("[green]Creating...[/green]"):
        try:
            pr = forge.create_pr(title, body if body else "", from_branch, to_branch, draft)
            console.print(f"\n[bold green]✔ Created![/bold green] [link={pr.url}]{pr.url}[/link]")

            if "slack_webhook" in config:
                payload = {
                    "text": f"🚀 *New PR* in `{ctx}`\n*Title:* {title}\n*Author:* {forge.get_user()}\n*Link:* {pr.url}"
                }
                try:
                    requests.post(config["slack_webhook"], json=payload, timeout=5)
                    console.print("[dim]✔ Slack notification sent.[/dim]")
                except Exception as e:
                    console.print(f"[yellow]⚠ Failed to send Slack notification: {e}[/yellow]")
        except Exception as e:
            console.print(f"[red]Failed:[/red] {e}")

@app.command()
def diff(
    pr_number: int, 
    repo_context: str = typer.Argument(None, help="Optional: org/repo override"),
    show_all: bool = typer.Option(False, "--all", "-a")
):
    """View Changes (Diffs) - Read Only."""
    ctx = repo_context or get_current_repo_context()
    forge = get_forge(ctx)
    
    console.rule(f"[bold blue]Diff View: #{pr_number}[/bold blue]")
    with console.status("Fetching files..."):
        files = forge.get_files(pr_number)
        
    table = Table(title="Changed Files")
    table.add_column("File", style="cyan")
    table.add_column("Stats", justify="right")
    for f in files:
        table.add_row(f.filename, f"+{f.additions} -{f.deletions}")
    console.print(table)
    
    if not show_all and not typer.confirm("View diffs?"): raise typer.Exit()
    
    for f in files:
        console.rule(f"[yellow]{f.filename}[/yellow]")
        if f.patch:
            console.print(Syntax(f.patch, "diff", theme="monokai", line_numbers=False))
        else:
            console.print("[dim]No diff available[/dim]")
        if not show_all: typer.prompt("Next...", show_default=False)

@app.command()
def review(
    pr_number: int,
    repo_context: str = typer.Argument(None, help="Optional: org/repo override")
):
    """Approve or Request Changes."""
    ctx = repo_context or get_current_repo_context()
    forge = get_forge(ctx)
    pr = forge.get_pr(pr_number)
    
    console.print(f"[bold]{pr.title}[/bold] by {pr.author}")
    action = typer.prompt("Action? (approve/request/comment/skip)").lower()
    
    event_map = {"approve": "APPROVE", "request": "REQUEST_CHANGES", "comment": "COMMENT"}
    if action not in event_map: raise typer.Exit()
    
    msg = typer.prompt("Message")
    forge.submit_review(pr_number, event_map[action], msg)
    console.print("[green]✔ Review Submitted.[/green]")

@app.command()
def edit(
    pr_number: int,
    repo_context: str = typer.Argument(None, help="Optional: org/repo override")
):
    """Edit Title/Description."""
    ctx = repo_context or get_current_repo_context()
    forge = get_forge(ctx)
    pr = forge.get_pr(pr_number)
    
    console.rule(f"[bold blue]Editing #{pr_number}[/bold blue]")
    new_title = typer.prompt("Title", default=pr.title)
    new_body = typer.edit(pr.body, extension=".md")
    
    with console.status("Updating..."):
        forge.edit_pr(pr_number, title=new_title, body=new_body if new_body else pr.body)
    console.print("[green]✔ Updated![/green]")

@app.command()
def comment(
    pr_number: int,
    repo_context: str = typer.Argument(None, help="Optional: org/repo override")
):
    """Add a comment."""
    ctx = repo_context or get_current_repo_context()
    forge = get_forge(ctx)
    
    console.print(f"Opening editor for PR #{pr_number}...")
    
    # Robust Notepad-safe logic
    body = typer.edit(
        "\n\n# Type your comment above.\n# Remember to SAVE (Ctrl+S) before closing the editor!\n# Lines starting with '#' will be ignored.", 
        extension=".md"
    )

    if not body:
        console.print("[yellow]⚠ Comment aborted (No text detected).[/yellow]")
        raise typer.Exit()

    # Clean up the placeholder text
    clean_body = "\n".join(
        [line for line in body.splitlines() if not line.strip().startswith("#")]
    ).strip()

    if not clean_body:
        console.print("[yellow]⚠ Comment aborted (Empty after cleaning).[/yellow]")
        raise typer.Exit()

    with console.status("[green]Posting comment...[/green]"):
        try:
            url = forge.comment(pr_number, clean_body)
            console.print(f"[bold green]✔ Comment posted successfully![/bold green]")
            if url:
                console.print(f"[link={url}]{url}[/link]")
        except Exception as e:
            console.print(f"[red]❌ Failed to post comment:[/red] {e}")

@app.command()
def cleanup(
    branch: str, 
    repo_context: str = typer.Argument(None, help="Optional: org/repo override"),
    force: bool = typer.Option(False, "--force", "-f", help="Delete even if unmerged")
):
    """Safely delete a branch (Remote & Local)."""
    ctx = repo_context or get_current_repo_context()
    forge = get_forge(ctx)
    
    try:
        local_repo = Repo(".", search_parent_directories=True)
    except Exception as e:
        console.print(f"[red]Could not load local git repo:[/red] {e}")
        raise typer.Exit(1)

    console.rule(f"[bold red]Janitor: {branch}[/bold red]")

    # 1. Check Remote Status
    with console.status(f"Checking if '{branch}' is merged..."):
        try:
            refs = local_repo.git.ls_remote("--heads", "origin", branch)
            if not refs:
                console.print(f"[yellow]⚠ Remote branch '{branch}' does not exist.[/yellow]")
            else:
                if not force:
                    confirm = typer.confirm(f"Are you sure you want to delete remote branch 'origin/{branch}'?", default=False)
                    if not confirm:
                        console.print("[red]Aborted.[/red]")
                        raise typer.Exit()

                # Delete Remote
                local_repo.git.push("origin", "--delete", branch)
                console.print(f"[green]✔ Deleted remote branch 'origin/{branch}'[/green]")

        except typer.Exit:
            raise
        except Exception as e:
            console.print(f"[red]Error handling remote:[/red] {e}")

    # 2. Delete Local
    try:
        if branch in local_repo.heads:
            if not force:
                try:
                    # --- SECURITY FIX: -- Separator ---
                    local_repo.git.branch("-d", "--", branch)
                    console.print(f"[green]✔ Deleted local branch '{branch}'[/green]")
                except git.exc.GitCommandError:
                    console.print(f"[red]⚠ Branch '{branch}' is not fully merged.[/red]")
                    console.print("Use [bold]--force[/bold] to delete anyway.")
            else:
                # Force delete (-D)
                local_repo.git.branch("-D", "--", branch)
                console.print(f"[green]✔ Force deleted local branch '{branch}'[/green]")
        else:
             console.print(f"[dim]Local branch '{branch}' not found.[/dim]")

    except Exception as e:
        console.print(f"[red]Failed to delete local:[/red] {e}")

@app.command()
def link(
    filepath: str,
    repo_context: str = typer.Argument(None, help="Optional: org/repo override"),
    lines: str = typer.Option(None, "--lines", "-l", help="Specific lines (e.g. 10-20)")
):
    """Generate a permalink to a file or image."""
    
    # --- SECURITY FIX: Prevent Path Traversal ---
    if ".." in filepath:
        console.print("[red]❌ Security Warning: Path traversal ('..') is not allowed.[/red]")
        raise typer.Exit(1)

    ctx = repo_context or get_current_repo_context()
    forge = get_forge(ctx)

    try:
        local_repo = Repo(".", search_parent_directories=True)
        commit_sha = local_repo.head.commit.hexsha
    except Exception as e:
        console.print(f"[red]Failed to get local commit SHA:[/red] {e}")
        console.print("Are you running this inside a git directory?")
        raise typer.Exit(1)

    # Determine Base URL
    config = load_config()
    provider = "github"
    if isinstance(forge, GitLabForge):
        provider = "gitlab"
    
    base = config[provider]["base_url"]

    # Construct URL based on forge formatting
    if provider == "github":
        domain = base.replace("api.", "").replace("/api/v3", "")
        url = f"{domain}/{ctx}/blob/{commit_sha}/{filepath}"
        if lines:
            if "-" in lines:
                start, end = lines.split("-")
                url += f"#L{start}-L{end}"
            else:
                url += f"#L{lines}"
    else:
        domain = base.replace("/api/v4", "")
        url = f"{domain}/{ctx}/-/blob/{commit_sha}/{filepath}"
        if lines:
            url += f"#L{lines}"
            
    console.print(f"\n[bold green]✔ Link Generated:[/bold green]\n{url}")


def main():
    app()

if __name__ == "__main__":
    main()