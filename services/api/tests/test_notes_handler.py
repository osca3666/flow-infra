import os
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-2")
os.environ.setdefault("AWS_REGION", "us-east-2")
os.environ.setdefault("TABLE_NAME", "FlowNotes")
import json
import boto3
import pytest
from moto import mock_aws


from services.api.lambdas.notes.handler import handler

def _event(method, path, body=None, sub="user-123"):
    return {
        "rawPath": path,
        "requestContext": {
            "http": {"method": method},
            "authorizer": {"jwt": {"claims": {"sub": sub}}},
        },
        "body": json.dumps(body) if body is not None else None,
    }

@mock_aws
def test_notes_crud():
    # Create table
    ddb = boto3.client("dynamodb", region_name="us-east-2")
    ddb.create_table(
        TableName="FlowNotes",
        BillingMode="PAY_PER_REQUEST",
        KeySchema=[
            {"AttributeName": "userId", "KeyType": "HASH"},
            {"AttributeName": "noteId", "KeyType": "RANGE"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "userId", "AttributeType": "S"},
            {"AttributeName": "noteId", "AttributeType": "S"},
        ],
    )

    os.environ["TABLE_NAME"] = "FlowNotes"

    # POST /notes
    res = handler(_event("POST", "/notes", {"content": "hello"}), None)
    assert res["statusCode"] == 201
    note = json.loads(res["body"])["item"]
    note_id = note["noteId"]

    # GET /notes
    res = handler(_event("GET", "/notes"), None)
    assert res["statusCode"] == 200
    items = json.loads(res["body"])["items"]
    assert len(items) == 1

    # PUT /notes/{id}
    res = handler(_event("PUT", f"/notes/{note_id}", {"content": "updated"}), None)
    assert res["statusCode"] == 200
    updated = json.loads(res["body"])["item"]
    assert updated["content"] == "updated"

    # DELETE /notes/{id}
    res = handler(_event("DELETE", f"/notes/{note_id}"), None)
    assert res["statusCode"] == 204
