import json 
import os
import time
import uuid
import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError
from decimal import Decimal


def _table():
    dynamodb = boto3.resource("dynamodb")
    table_name = os.environ["TABLE_NAME"]
    return dynamodb.Table(table_name)

def _json_default(o):
    if isinstance(o, Decimal):
        # DynamoDB uses Decimal for numbers, conversion needed 
        return int(o) if o % 1 == 0 else float(o)
    raise TypeError


def _resp(status: int, body: dict):
    return {
        "statusCode": status,
        "headers": {"content-type": "application/json"},
        "body": json.dumps(body, default=_json_default),
    }

def _get_user_id(event) -> str | None:
    claims = (
        event.get("requestContext", {})
        .get("authorizer", {})
        .get("jwt", {})
        .get("claims", {})
    )
    return claims.get("sub")

def handler(event, context):
    method = event.get("requestContext", {}).get("http", {}).get("method")
    path = event.get("rawPath", "")
    user_id = _get_user_id(event)

    if not user_id:
        return _resp(401, {"message": "Unauthorized"})
    
    # Routes:
    # GET    /notes
    if path == "/notes" and method == "GET":
        result = _table().query(
            KeyConditionExpression=Key("userId").eq(user_id),
        )
        items = result.get("Items", [])

        items = sorted(items, key=lambda x: x.get("createdAt", 0), reverse=True)

        return _resp(200, {"items": items})

    
    # POST   /notes
    if path == "/notes" and method == "POST":
        try: 
            body = json.loads(event.get("body") or "{}")
        except json.JSONDecodeError:
            return _resp(400, {"message": "Invalid JSON body"})
        
        content = (body.get("content") or "").strip()
        if not content: 
            return _resp(400, {"message": "content is required"})
        
        now = int(time.time())
        note_id = str(uuid.uuid4())

        item = {
            "userId": user_id,
            "noteId": note_id,
            "content": content,
            "createdAt": now,
            "updatedAt": now,
        }
        _table().put_item(Item=item)

        return _resp(201, {"item": item})
    
    if path.startswith("/notes/"):
        note_id = path.split("/notes/")[1].strip()
        if not note_id:
            return _resp(404, {"message": "Not found"})
    
        # PUT    /notes/{id}
        if method == "PUT":
            try:
                body = json.loads(event.get("body") or "{}")
            except json.JSONDecodeError:
                return _resp(400, {"message": "Invalid JSON body"})

            content = (body.get("content") or "").strip()
            if not content: 
                return _resp(400, {"message": "content is required"})

            now = int(time.time())   
            # Ensure user can only update their own item (key includes userId)       

            try:
                result = _table().update_item(
                    Key = {"userId": user_id, "noteId": note_id},
                    UpdateExpression="SET content = :c, updatedAt = :u",
                    ExpressionAttributeValues={":c": content, ":u": now},
                    ConditionExpression="attribute_exists(noteId)",
                    ReturnValues="ALL_NEW",
                )
            except ClientError as e:
                if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                    return _resp(404, {"message": "Not found"})
                raise  # re-raise unexpected errors
            
            return _resp(200, {"item": result.get("Attributes")})
              

        # DELETE /notes/{id}
        if method == "DELETE":
            _table().delete_item(Key={"userId": user_id, "noteId": note_id})
            return _resp(204, {})

    return _resp(404, {"message": "Not found"})
