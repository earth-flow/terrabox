"""Routes related to user registration and account connections."""

from __future__ import annotations

import secrets
import uuid
from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel

from ..data import (
    add_connection,
    add_user,
    find_user_by_api_key,
    add_connected_account,
    get_connection,
    get_connected_accounts_for_user,
    get_connected_account,
    remove_connected_account,
)
from ..models import Connection, ConnectedAccount, User


router = APIRouter(prefix="/v1", tags=["auth"])


class RegisterRequest(BaseModel):
    user_id: str


class RegisterResponse(BaseModel):
    api_key: str


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
def register_user(payload: RegisterRequest):
    """Register a new user and issue an API key.

    Clients must register before interacting with any other endpoints.
    The returned API key must be provided in the ``X-API-Key`` header
    for all subsequent requests.  Duplicate registrations for the
    same user ID will return a new API key, invalidating the
    previous key.
    """
    # Generate a random API key
    api_key = secrets.token_hex(16)
    user = User(user_id=payload.user_id, api_key=api_key)
    add_user(user)
    return RegisterResponse(api_key=api_key)


class CreateConnectionRequest(BaseModel):
    toolkit: str
    user_id: str


class CreateConnectionResponse(BaseModel):
    connection_id: str
    redirect_url: str
    status: str


@router.post("/auth/connections", response_model=CreateConnectionResponse, status_code=status.HTTP_201_CREATED)
def create_connection(payload: CreateConnectionRequest, x_api_key: str = Header(...)):
    """Initiate an OAuth connection for a toolkit.

    Returns a connection identifier and a redirect URL which the
    client should open in a browser.  The platform will mark the
    connection as authorised when the user completes the flow.  For
    this simplified implementation authorisation occurs when the
    client polls the connection status.
    """
    # Authenticate the caller
    user = find_user_by_api_key(x_api_key)
    if user is None or user.user_id != payload.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid API key or user ID")
    # Create connection
    conn = Connection(
        user_id=payload.user_id,
        toolkit=payload.toolkit,
        redirect_url=f"https://auth.example.com/{uuid.uuid4()}"
    )
    add_connection(conn)
    return CreateConnectionResponse(
        connection_id=conn.id,
        redirect_url=conn.redirect_url,
        status=conn.status,
    )


class ConnectionStatusResponse(BaseModel):
    connection_id: str
    status: str
    connected_account_id: str | None = None


@router.get("/auth/connections/{connection_id}", response_model=ConnectionStatusResponse)
def get_connection_status(connection_id: str, x_api_key: str = Header(...)):
    """Check the status of a connection.

    Poll this endpoint to determine when the user has finished the
    third‑party OAuth flow.  When the status transitions to
    ``authorized`` a connected account record will have been
    created.
    """
    user = find_user_by_api_key(x_api_key)
    if user is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid API key")
    conn = get_connection(connection_id)
    if conn is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connection not found")
    # Only allow the owning user to query
    if conn.user_id != user.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorised to view this connection")
    # Simulate user completing OAuth on first poll
    if conn.status == "pending":
        # Create connected account
        display_name = f"{conn.toolkit} account for {conn.user_id}"
        acc = ConnectedAccount(user_id=conn.user_id, toolkit=conn.toolkit, display_name=display_name, token=secrets.token_hex(8))
        add_connected_account(acc)
        conn.status = "authorized"
        conn.connected_account_id = acc.id
    return ConnectionStatusResponse(
        connection_id=conn.id,
        status=conn.status,
        connected_account_id=conn.connected_account_id,
    )


class ConnectedAccountOut(BaseModel):
    id: str
    user_id: str
    toolkit: str
    display_name: str
    status: str


@router.get("/auth/connected-accounts", response_model=list[ConnectedAccountOut])
def list_connected_accounts(user_id: str, toolkit: str | None = None, x_api_key: str = Header(...)):
    """List all connected accounts for a user.

    The API key must belong to the given user.  Optionally filter
    by toolkit name.
    """
    user = find_user_by_api_key(x_api_key)
    if user is None or user.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid API key or user ID")
    accounts = get_connected_accounts_for_user(user_id, toolkit)
    return [
        ConnectedAccountOut(
            id=acc.id,
            user_id=acc.user_id,
            toolkit=acc.toolkit,
            display_name=acc.display_name,
            status="active",
        )
        for acc in accounts
    ]


@router.delete("/auth/connected-accounts/{connected_account_id}", response_model=ConnectedAccountOut)
def revoke_connected_account(connected_account_id: str, x_api_key: str = Header(...)):
    """Revoke (delete) a connected account.

    Only the owning user may revoke their account.  Returns the
    deleted record.
    """
    user = find_user_by_api_key(x_api_key)
    if user is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid API key")
    acc = get_connected_account(connected_account_id)
    if acc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connected account not found")
    if acc.user_id != user.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorised to remove this account")
    remove_connected_account(connected_account_id)
    return ConnectedAccountOut(
        id=acc.id,
        user_id=acc.user_id,
        toolkit=acc.toolkit,
        display_name=acc.display_name,
        status="revoked",
    )
