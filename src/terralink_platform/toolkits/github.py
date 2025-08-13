"""GitHub toolkit plugin for the Terralink platform.

This module provides GitHub-related tools that can interact with
GitHub repositories and issues. It demonstrates how to migrate
existing tools to the new plugin system.
"""

from typing import Any, Dict, Optional

from ..models import ToolSpec, ConnectedAccount


def _gh_sample_repos(username: str) -> list[str]:
    """Return a deterministic list of sample repositories for a user.

    In lieu of real GitHub API calls this helper produces a
    predictable set of repository names based on the input
    ``username``.  Each user will have up to three repos whose
    names incorporate the username.
    """
    base = username.strip().lower() or "default"
    return [f"{base}-repo-{n}" for n in range(1, 4)]


def list_user_repos_handler(arguments: Dict[str, Any], context: Dict[str, Any], account: Optional[ConnectedAccount]) -> Dict[str, Any]:
    """Handler for listing GitHub user repositories.
    
    Parameters
    ----------
    arguments : Dict[str, Any]
        Tool arguments containing 'username'
    context : Dict[str, Any]
        Execution context
    account : Optional[ConnectedAccount]
        Connected account (not required for this tool)
        
    Returns
    -------
    Dict[str, Any]
        Dictionary containing list of repositories
    """
    username = arguments.get("username")
    repos = _gh_sample_repos(username)
    return {"repositories": repos}


def create_issue_handler(arguments: Dict[str, Any], context: Dict[str, Any], account: Optional[ConnectedAccount]) -> Dict[str, Any]:
    """Handler for creating GitHub issues.
    
    Parameters
    ----------
    arguments : Dict[str, Any]
        Tool arguments containing 'repository', 'title', and optional 'body'
    context : Dict[str, Any]
        Execution context
    account : Optional[ConnectedAccount]
        Connected account (required for this tool)
        
    Returns
    -------
    Dict[str, Any]
        Dictionary containing created issue information
        
    Raises
    ------
    ValueError
        If no connected account is provided
    """
    # In a real implementation the connected account's token would be
    # used to authenticate with GitHub.  Here we just return a
    # stubbed issue record and increment an internal counter per
    # connected account.
    if account is None:
        raise ValueError("No connected account provided")
    
    repository = arguments.get("repository")
    title = arguments.get("title")
    body = arguments.get("body")
    
    # Determine a deterministic issue number based on repository and user id
    issue_num = abs(hash((repository, account.user_id))) % 1000 + 1
    
    return {
        "repository": repository,
        "issue_number": issue_num,
        "title": title,
        "body": body or "",
    }


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
        description="List repositories owned by a user",
        parameters={
            "type": "object",
            "properties": {
                "username": {
                    "type": "string",
                    "description": "GitHub username whose repositories to list",
                }
            },
            "required": ["username"],
        },
        toolkit="github",
        requires_connection=False,
    )
    registrar.tool(list_repos_spec, list_user_repos_handler)
    
    # Register the create issue tool
    create_issue_spec = ToolSpec(
        slug="github.create_issue",
        description="Create an issue in a GitHub repository",
        parameters={
            "type": "object",
            "properties": {
                "repository": {
                    "type": "string",
                    "description": "Repository where the issue will be created",
                },
                "title": {
                    "type": "string",
                    "description": "Title of the issue",
                },
                "body": {
                    "type": "string",
                    "description": "Issue body text",
                },
            },
            "required": ["repository", "title"],
        },
        toolkit="github",
        requires_connection=True,
    )
    registrar.tool(create_issue_spec, create_issue_handler)