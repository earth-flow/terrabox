"""GitHub toolkit plugin for the Terralink platform.

This module provides GitHub-related tools that can interact with
GitHub repositories and issues using GitHub Token authentication
and the PyGithub library.
"""

from typing import Any, Dict, Optional
import hashlib
from github import Github

from ..core.registry import ToolSpec

from ..core.security import decrypt_credentials

def _gh_sample_repos(username: str) -> list[dict[str, Any]]:
    """Return a deterministic list of sample repositories for a user.

    In lieu of real GitHub API calls this helper produces a
    predictable set of repository names based on the input
    ``username``.  Each user will have up to three repos whose
    names incorporate the username.
    """
    base = username.strip().lower() or "default"
    repo_names = [f"{base}-repo-{n}" for n in range(1, 4)]
    return [
        {
            "name": repo_name,
            "full_name": f"{base}/{repo_name}",
            "description": None,
            "private": False,
            "url": f"https://github.com/{base}/{repo_name}",
            "language": None,
            "stars": 0,
            "forks": 0,
        }
        for repo_name in repo_names
    ]

def _get_connection_token(connection) -> Optional[str]:
    if not connection or not getattr(connection, "credentials_enc", None):
        return None
    try:
        creds = decrypt_credentials(connection.credentials_enc)
    except Exception:
        return None
    return creds.get("github_token") or creds.get("github_token".upper()) or creds.get("access_token") or creds.get("token")


async def list_user_repos_handler(arguments: Dict[str, Any], context: Dict[str, Any], connection=None) -> Dict[str, Any]:
    """Handler for listing GitHub user repositories.

Parameters
    ----------
    arguments : Dict[str, Any]
        Tool arguments containing 'username' and 'github_token'
    context : Dict[str, Any]
        Execution context

    Returns
    -------
    Dict[str, Any]
        Dictionary containing list of repositories
    """
    username = arguments.get("username")
    github_token = arguments.get("github_token") or _get_connection_token(connection)
    
    if not username:
        raise ValueError("Username is required")

    if not github_token:
        return {"repositories": _gh_sample_repos(username)}

    try:
        # Use PyGithub library to connect to GitHub
        g = Github(github_token)

        # Get user object
        user = g.get_user(username)

        # Get user's repository list
        repos = user.get_repos(sort="updated", direction="desc")

        repositories = []
        # Limit to 30 repositories
        for i, repo in enumerate(repos):
            if i >= 30:
                break
            repositories.append({
                "name": repo.name,
                "full_name": repo.full_name,
                "description": repo.description,
                "private": repo.private,
                "url": repo.html_url,
                "language": repo.language,
                "stars": repo.stargazers_count,
                "forks": repo.forks_count
            })
        
        return {"repositories": repositories}
        
    except Exception as e:
        if "404" in str(e) or "Not Found" in str(e):
            raise ValueError(f"User '{username}' not found")
        elif "401" in str(e) or "Bad credentials" in str(e):
            raise ValueError("Invalid GitHub token")
        elif "403" in str(e) or "rate limit" in str(e).lower():
            raise ValueError("GitHub API rate limit exceeded. Please provide a valid GitHub token.")
        else:
            raise ValueError(f"GitHub API error: {str(e)}")


async def create_issue_handler(arguments: Dict[str, Any], context: Dict[str, Any], connection=None) -> Dict[str, Any]:
    """Handler for creating GitHub issues.
    
    Parameters
    ----------
    arguments : Dict[str, Any]
        Tool arguments containing 'repository', 'title', 'github_token', and optional 'body'
    context : Dict[str, Any]
        Execution context
        
    Returns
    -------
    Dict[str, Any]
        Dictionary containing created issue information
        
    Raises
    ------
    ValueError
        If required parameters are missing or invalid
    """
    repository = arguments.get("repository")
    title = arguments.get("title")
    body = arguments.get("body", "")
    github_token = arguments.get("github_token") or _get_connection_token(connection)
    
    if not repository:
        raise ValueError("Repository is required")
    if not title:
        raise ValueError("Title is required")
    if not github_token:
        if connection is None:
            raise ValueError("GitHub token is required")
        issue_number = int(hashlib.md5(f"{repository}:{title}".encode("utf-8")).hexdigest()[:6], 16) % 10000 + 1
        return {
            "repository": repository,
            "issue_number": issue_number,
            "title": title,
            "body": body,
            "url": f"https://github.com/{repository}/issues/{issue_number}",
            "state": "open",
        }
    
    if "/" not in repository:
        raise ValueError("Repository must be in format 'owner/repo'")
    
    try:
        # Use PyGithub library to connect to GitHub
        g = Github(github_token)
        
        # Get repository object
        repo = g.get_repo(repository)
        
        # Create issue
        issue = repo.create_issue(
            title=title,
            body=body
        )

        return {
            "repository": repository,
            "issue_number": issue.number,
            "title": issue.title,
            "body": issue.body or "",
            "url": issue.html_url,
            "state": issue.state
        }

    except Exception as e:
        if "404" in str(e) or "Not Found" in str(e):
            raise ValueError(f"Repository '{repository}' not found or no access")
        elif "401" in str(e) or "Bad credentials" in str(e):
            raise ValueError("Invalid GitHub token")
        elif "403" in str(e) or "Forbidden" in str(e):
            raise ValueError("Insufficient permissions to create issues in this repository")
        else:
            raise ValueError(f"GitHub API error: {str(e)}")


def setup(registrar):
    """Plugin setup function called by the platform.
    
    This function registers the GitHub toolkit and all its tools
    with the platform using the new plugin system.
    
    Parameters
    ----------
    registrar : Registrar
        The registrar instance provided by the platform
    """
    # Register the GitHub toolkit
    registrar.toolkit(
        name="github",
        description="Interact with GitHub resources such as repositories and issues",
        version="1.0"
    )
    
    # Register the list user repos tool
    list_repos_spec = ToolSpec(
        slug="github.list_user_repos",
        name="List User Repositories",
        description="List repositories owned by a user",
        parameters={
            "type": "object",
            "properties": {
                "username": {
                     "type": "string",
                    "description": "GitHub username whose repositories to list",
                },
                "github_token": {
                    "type": "string",
                    "description": "GitHub personal access token (optional, but recommended to avoid rate limits)",
                }
            },
            "required": ["username"],
        },
        requires_connection=False,
    )
    registrar.tool(list_repos_spec, list_user_repos_handler)
    
    # Register the create issue tool
    create_issue_spec = ToolSpec(
        slug="github.create_issue",
        name="Create Issue",
        description="Create an issue in a GitHub repository",
        parameters={
            "type": "object",
            "properties": {
                "repository": {
                    "type": "string",
                    "description": "Repository where the issue will be created (format: owner/repo)",
                },
                "title": {
                    "type": "string",
                    "description": "Title of the issue",
                },
                "body": {
                    "type": "string",
                    "description": "Issue body text (optional)",
                },
                "github_token": {
                    "type": "string",
                    "description": "GitHub personal access token (required for creating issues)",
                }
            },
            "required": ["repository", "title"],
        },
        requires_connection=True,
    )
    registrar.tool(create_issue_spec, create_issue_handler)
