import typer
import json
import requests
import re
from pathlib import Path
from typing import Optional
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from github import Github, GithubException
from git import Repo, InvalidGitRepositoryError

# --- CONFIGURATION & SETUP ---
app = typer.Typer(help="The Exclusive GitHub CLI Tool")
console = Console()
APP_NAME = "gitpr"
CONFIG_PATH = Path(typer.get_app_dir(APP_NAME)) / "config.json"

# --- HELPERS ---

def load_config():
    """Loads config securely from local system."""
    if not CONFIG_PATH.exists():
        console.print("[bold red]Not logged in.[/bold red] Please run `gitpr login` first.")
        raise typer.Exit(code=1)
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)

def get_github_client(config):
    """
    Initializes GitHub client and verifies the token is valid.
    Handles expired tokens gracefully.
    """
    g = Github(base_url=config["base_url"], login_or_token=config["token"])
    
    try:
        # Lightweight call to verify token validity
        _ = g.get_user().login
    except GithubException as e:
        if e.status == 401: # Unauthorized / Expired
            console.print("[bold red]❌ Authentication Failed.[/bold red]")
            console.print("Your token has expired or is invalid.")
            console.print(f"[yellow]Action:[/yellow] Please run [bold]gitpr login[/bold] to update your token.")
            raise typer.Exit(code=1)
        else:
            raise e
    return g

def get_current_repo_context():
    """Detects org/repo from the current directory's .git folder."""
    try:
        repo = Repo(".", search_parent_directories=True)
        remote_url = repo.remotes.origin.url
        # Parse SSH (git@github.com:org/repo.git) or HTTPS (https://github.com/org/repo.git)
        match = re.search(r"[:/]([\w-]+)/([\w-]+)(?:\.git)?$", remote_url)
        if match:
            return f"{match.group(1)}/{match.group(2)}"
        return None
    except (InvalidGitRepositoryError, AttributeError):
        return None

# --- COMMANDS ---

@app.command()
def login():
    """
    Setup GitHub Token, Enterprise URL, and optional Slack Webhook.
    """
    console.print(Panel("[bold blue]GitPR Setup Wizard[/bold blue]", expand=False))
    
    # 1. GitHub Enterprise Logic
    is_enterprise = typer.confirm("Are you using GitHub Enterprise?", default=False)
    base_url = "https://api.github.com"
    if is_enterprise:
        domain = typer.prompt("Enter Enterprise Domain (e.g. github.acme.com)")
        base_url = f"https://{domain}/api/v3"

    # 2. Token
    console.print(f"\n[dim]Create a token at: {base_url.replace('/api/v3', '')}/settings/tokens[/dim]")
    token = typer.prompt("Paste your GitHub Token", hide_input=True)

    # 3. Slack (Optional)
    setup_slack = typer.confirm("Do you want to configure Slack notifications?", default=False)
    slack_webhook = None
    if setup_slack:
        slack_webhook = typer.prompt("Paste Slack Webhook URL")

    # 4. Save
    if not CONFIG_PATH.parent.exists():
        CONFIG_PATH.parent.mkdir(parents=True)
        
    config_data = {
        "token": token,
        "base_url": base_url,
        "slack_webhook": slack_webhook
    }
    
    with open(CONFIG_PATH, "w") as f:
        json.dump(config_data, f)
    
    CONFIG_PATH.chmod(0o600) # Secure file
    console.print(f"[green]✔ Configuration saved to {CONFIG_PATH}[/green]")


@app.command()
def create(
    repo_arg: Optional[str] = typer.Argument(None, help="org/repo. Auto-detected if missing."),
    from_branch: str = typer.Option(..., "--from", "-f", help="Source Branch"),
    to_branch: str = typer.Option(..., "--to", "-t", help="Target Branch"),
    draft: bool = typer.Option(False, "--draft", help="Create as Draft PR")
):
    """
    Creates a PR with interactive Title/Body, Template support, and Issue Linking.
    """
    config = load_config()
    
    # 1. Repo Detection
    if not repo_arg:
        repo_arg = get_current_repo_context()
        if not repo_arg:
            console.print("[red]❌ Could not detect repository. Run command inside a git folder or provide org/repo argument.[/red]")
            raise typer.Exit(1)
    
    # 2. Authenticate & Connect
    with console.status("[dim]Verifying credentials...[/dim]"):
        g = get_github_client(config)
        try:
            repo = g.get_repo(repo_arg)
        except GithubException:
            console.print(f"[red]❌ Access denied to {repo_arg}. Check token scopes.[/red]")
            raise typer.Exit(1)

    # 3. Interactive Inputs
    console.rule(f"[bold blue]Creating PR: {repo_arg}[/bold blue]")
    title = typer.prompt("Enter PR Title")

    # 4. Template & Body (Vim)
    template_content = ""
    # Try fetching template
    for path in [".github/pull_request_template.md", "pull_request_template.md", "docs/pull_request_template.md",
                 ".github/PULL_REQUEST_TEMPLATE.md", "PULL_REQUEST_TEMPLATE.md", "docs/PULL_REQUEST_TEMPLATE.md"]:
        try:
            template_content = repo.get_contents(path, ref=to_branch).decoded_content.decode()
            break
        except:
            pass

    if template_content:
        console.print(Panel(Markdown(template_content), title="Template Found", border_style="yellow"))
        console.print("[dim]Press Enter to open editor...[/dim]")
        typer.wait_for_keypress()
    
    # Opens Vim (or default editor)
    body = typer.edit(template_content if template_content else "", extension=".md")

    if not body:
        if not typer.confirm("Body is empty. Continue?"):
            raise typer.Exit()
        body = ""

    # 5. Create PR via API
    with console.status("[bold green]Submitting PR...[/bold green]"):
        try:
            pr = repo.create_pull(
                title=title,
                body=body,
                head=from_branch,
                base=to_branch,
                draft=draft
            )
        except GithubException as e:
            console.print(f"[red]Failed:[/red] {e.data.get('message', e)}")
            raise typer.Exit(1)

    console.print(f"\n[bold green]✔ PR Created Successfully![/bold green]")
    console.print(f"🔗 Link: [link={pr.html_url}]{pr.html_url}[/link]")

    # 6. Issue Linking Logic (User Request: Ask Y/N -> Link -> Comment on Issue)
    if typer.confirm("Link this PR to an Issue?"):
        issue_url = typer.prompt("Enter Issue URL")
        
        # FIX: Regex now looks for the path pattern /org/repo/issues/number
        # This works for github.com, github.ibm.com, or any enterprise domain.
        match = re.search(r"/([\w-]+)/([\w-]+)/issues/(\d+)", issue_url)
        
        if match:
            tgt_org, tgt_repo_name, tgt_issue_num = match.groups()
            try:
                # We reuse the existing 'g' client which is already authenticated
                # to the correct Enterprise or Public domain.
                tgt_repo = g.get_repo(f"{tgt_org}/{tgt_repo_name}")
                tgt_issue = tgt_repo.get_issue(int(tgt_issue_num))
                
                # Add comment to the issue
                tgt_issue.create_comment(f"PR Created: {pr.html_url}")
                console.print(f"[green]✔ Comment added to Issue #{tgt_issue_num}[/green]")
            except Exception as e:
                console.print(f"[red]Failed to comment on issue: {e}[/red]")
        else:
            console.print("[yellow]Invalid Issue URL format. Skipping.[/yellow]")

    # 7. Slack Notification (Feature 4)
    if config.get("slack_webhook"):
        payload = {
            "text": f"🚀 *New PR Created* in `{repo_arg}`\n*Title:* {title}\n*Link:* {pr.html_url}\n*Author:* {g.get_user().login}"
        }
        try:
            requests.post(config["slack_webhook"], json=payload)
            console.print("[blue]✔ Slack notification sent.[/blue]")
        except Exception:
            console.print("[yellow]⚠ Failed to send Slack notification.[/yellow]")


@app.command()
def comment(
    pr_number: int,
    repo_arg: Optional[str] = typer.Argument(None, help="org/repo. Auto-detected if missing.")
):
    """
    Adds a comment to an existing PR using Vim editor.
    """
    config = load_config()
    
    # 1. Repo Detection
    if not repo_arg:
        repo_arg = get_current_repo_context()
        if not repo_arg:
            console.print("[red]❌ Could not detect repository.[/red]")
            raise typer.Exit(1)

    # 2. Authenticate & Check PR
    g = get_github_client(config)
    try:
        repo = g.get_repo(repo_arg)
        pr = repo.get_pull(pr_number)
    except GithubException:
        console.print(f"[bold red]PR #{pr_number} not found in {repo_arg}[/bold red]")
        raise typer.Exit(1)

    # 3. Open Editor
    console.print(f"[blue]Adding comment to PR #{pr_number} ({pr.title})[/blue]")
    console.print("[dim]Opening editor... Write your comment (Markdown supported).[/dim]")
    
    # Opens editor for comment body
    comment_body = typer.edit(extension=".md")

    if not comment_body or not comment_body.strip():
        console.print("[yellow]Comment empty. Aborted.[/yellow]")
        raise typer.Exit()

    # 4. Submit
    with console.status("[green]Posting comment...[/green]"):
        pr.create_issue_comment(comment_body)
    
    console.print(f"[bold green]✔ Comment added to PR #{pr_number}[/bold green]")

def main():
    app()

if __name__ == "__main__":
    main()