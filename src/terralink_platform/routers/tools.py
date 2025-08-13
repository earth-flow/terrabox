"""Routes for toolkits and tool execution."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, status
import uuid
from pydantic import BaseModel

from ..data import (
    find_user_by_api_key,
    get_tool,
    list_tools,
    list_toolkits,
    get_connected_account,
)
from ..extensions import get_handler
from ..models import ExecuteRequest, ExecuteResponse, ToolSpec, Toolkit


router = APIRouter(prefix="/v1", tags=["tools"])


class ToolSpecOut(BaseModel):
    slug: str
    description: str
    parameters: dict
    toolkit: str
    requires_connection: bool


@router.get("/tools", response_model=list[ToolSpecOut])
def get_tools(toolkit: str | None = None, connected_account_id: str | None = None, x_api_key: str = Header(...)):
    """Return a list of tool specifications.

    Clients must authenticate with their API key.  Tools may be
    filtered by toolkit name and connected account ID.  The response contains the slug,
    description and parameter schema for each tool.
    """
    user = find_user_by_api_key(x_api_key)
    if user is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid API key")
    
    specs = list_tools(toolkit)
    
    if connected_account_id:
        acc = get_connected_account(connected_account_id)
        if not acc or acc.user_id != user.user_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connected account not found")
        # TODO: Filter specs based on acc's scope/permissions
        # specs = filter_specs_by_scope(specs, acc.scopes)
    
    return [
        ToolSpecOut(
            slug=spec.slug,
            description=spec.description,
            parameters=spec.parameters,
            toolkit=spec.toolkit,
            requires_connection=spec.requires_connection,
        )
        for spec in specs
    ]


@router.get("/tools/{slug}", response_model=ToolSpecOut)
def get_tool_detail(slug: str, x_api_key: str = Header(...)):
    """Return the specification for a single tool."""
    if find_user_by_api_key(x_api_key) is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid API key")
    spec = get_tool(slug)
    if spec is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tool not found")
    return ToolSpecOut(
        slug=spec.slug,
        description=spec.description,
        parameters=spec.parameters,
        toolkit=spec.toolkit,
        requires_connection=spec.requires_connection,
    )


class ToolkitOut(BaseModel):
    name: str
    description: str
    version: str


@router.get("/toolkits", response_model=list[ToolkitOut])
def get_toolkits(x_api_key: str = Header(...)):
    """Return a list of available toolkits."""
    if find_user_by_api_key(x_api_key) is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid API key")
    metas = list_toolkits()
    return [ToolkitOut(name=meta.name, description=meta.description, version=meta.version) for meta in metas]


@router.post("/tools/{slug}/execute", response_model=ExecuteResponse)
def execute_tool(slug: str, payload: ExecuteRequest, x_api_key: str = Header(...)):
    """Execute a single tool.

    The caller must provide their API key and a context containing
    the user ID.  If the tool requires a connection a valid
    ``connected_account_id`` must be supplied in the context.
    """
    # Authenticate
    user = find_user_by_api_key(x_api_key)
    if user is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid API key")
    # Look up tool
    spec = get_tool(slug)
    if spec is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tool not found")
    # Validate context
    ctx = payload.context or {}
    user_id = ctx.get("user_id")
    connected_account_id = ctx.get("connected_account_id")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="context.user_id is required")
    if user_id != user.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User ID in context does not match API key")
    # Check connection if required
    account = None
    if spec.requires_connection:
        # If provided, verify existence and ownership
        if connected_account_id:
            account = get_connected_account(connected_account_id)
            if account is None or account.user_id != user_id or account.toolkit != spec.toolkit:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connected account not found or mismatched")
        else:
            # Attempt to auto‑select default account for toolkit
            from ..data import get_connected_accounts_for_user

            accounts = get_connected_accounts_for_user(user_id, spec.toolkit)
            if len(accounts) == 1:
                account = accounts[0]
            else:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Multiple connected accounts available; specify connected_account_id")
    # Get handler from plugin system
    handler = get_handler(slug)
    if handler is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="No handler registered for tool")
    
    # Execute tool logic
    try:
        result_data = handler(payload.arguments, ctx, account)
        return ExecuteResponse(ok=True, data=result_data, trace_id=str(uuid.uuid4()))
    except Exception as exc:
        return ExecuteResponse(ok=False, error=str(exc), trace_id=str(uuid.uuid4()))
