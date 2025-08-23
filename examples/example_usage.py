"""Example usage of the Terralink SDK against the platform service.

This script demonstrates how to register a user, initiate a
connection, list tools and execute them using the SDK.  To run
this example you must first start the Terralink platform locally:

.. code-block:: bash

    # From the root of this repository
    uvicorn terralink_platform.main:app --reload --port 8000

Then install the SDK in editable mode from the sibling `terralink`
directory and execute this script:

.. code-block:: bash

    cd terralink/packages/python
    pip install -e .
    cd ../../..
    python terralink_platform/examples/example_usage.py

The script will register a user, configure the SDK to talk to
``http://localhost:8000``, connect a GitHub account and create
an issue in a repository.  The operations are logged to
standard output.
"""

import os
import time
import uuid

from terralink import ToolsFacade
from terralink.models import ExecutionContext
from terralink.auth import connect_toolkit
from terralink.client import TerralinkClient


def main() -> None:
    # Set the base URL of the SDK to point at our local platform
    os.environ["TERRALINK_BASE_URL"] = "http://localhost:8000"
    # Step 1: register a new user via raw HTTP (we could use
    # TerralinkClient here as well)
    client = TerralinkClient(base_url="http://localhost:8000")
    user_id = f"user-{uuid.uuid4().hex[:8]}"
    print(f"Registering user {user_id}...")
    resp = client._http.post("/v1/register", json={"user_id": user_id})
    api_key = resp.json()["api_key"]
    print(f"Received API key {api_key}")
    # Configure the SDK to use this key
    os.environ["TERRALINK_API_KEY"] = api_key
    # Step 2: connect the GitHub toolkit (simulated OAuth flow)
    print("Connecting GitHub toolkit...")
    connected_account_id = connect_toolkit("github", user_id)
    print(f"Connected account id: {connected_account_id}")
    # Step 3: list available tools via the SDK
    tf = ToolsFacade()
    specs = tf.get(toolkit="github")
    print("Available GitHub tools:")
    for spec in specs:
        print(f" - {spec.slug}")
    # Step 4: execute a tool that does not require a connection
    ctx = ExecutionContext(user_id=user_id)
    result = tf.execute("github.list_user_repos", {"username": user_id}, ctx)
    print("List repos result:", result.data)
    # Step 5: execute a tool that requires a connection
    ctx2 = ExecutionContext(user_id=user_id, connected_account_id=connected_account_id)
    result = tf.execute(
        "github.create_issue",
        {"repository": f"{user_id}-repo-1", "title": "Hello", "body": "This is a test"},
        ctx2,
    )
    print("Create issue result:", result.data)


if __name__ == "__main__":
    main()
