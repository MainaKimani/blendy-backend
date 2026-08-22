"""Build the Postman collection (blendy-suite-v1.json) from swagger.json.

Regenerate both together, in this order:

    python manage.py generate_swagger swagger.json --overwrite
    python convert_swagger_to_postman.py

The collection is meant to be *runnable*, not just a list of URLs, so it carries
the three things every request against this API needs and the schema alone does
not supply:

* **Auth.** Collection-level bearer auth reading `{{access_token}}`. The login
  request captures the token into that variable automatically, so signing in
  once arms the whole collection.
* **Tenancy.** `X-Organization: {{organization_id}}` on every request whose
  operation declares the header. Without it the API fails closed and returns
  empty results rather than an error, which is a confusing way to discover you
  forgot a header.
* **Bodies without read-only fields.** The previous version rendered every
  property in the schema, including server-assigned ones like `id`,
  `created_at` and `total_price`. Sending those back is at best noise and at
  worst misleading about what a client is expected to supply.
"""

import json
from collections import OrderedDict

SWAGGER_FILE = "swagger.json"
POSTMAN_FILE = "blendy-suite-v1.json"

# Rendered for a property that has a format but no example, so the collection
# ships plausible values rather than the string "string" everywhere.
FORMAT_PLACEHOLDERS = {
    "uuid": "00000000-0000-0000-0000-000000000000",
    "decimal": "0.00",
    "date-time": "2026-01-01T09:00:00Z",
    "date": "2026-01-01",
    "email": "user@example.com",
    "uri": "https://example.com",
    "binary": "<file>",
}

# Captures the JWT so the rest of the collection can use it unattended.
LOGIN_TEST_SCRIPT = [
    "// Captures the JWT so every other request in this collection is authorised.",
    "if (pm.response.code === 200 || pm.response.code === 201) {",
    "    const body = pm.response.json();",
    "    if (body.access) {",
    "        pm.collectionVariables.set('access_token', body.access);",
    "    }",
    "    if (body.refresh) {",
    "        pm.collectionVariables.set('refresh_token', body.refresh);",
    "    }",
    "}",
]


def example_for_property(details, definitions, seen):
    if "example" in details:
        return details["example"]
    if "$ref" in details:
        return example_from_schema(details, definitions, seen)
    if "enum" in details and details["enum"]:
        return details["enum"][0]

    prop_type = details.get("type")
    if prop_type == "array":
        return [example_from_schema(details.get("items", {}), definitions, seen)]
    if prop_type == "object" or "properties" in details:
        return example_from_schema(details, definitions, seen)
    if prop_type == "integer":
        return 0
    if prop_type == "number":
        return 0
    if prop_type == "boolean":
        return False
    if prop_type == "string":
        return FORMAT_PLACEHOLDERS.get(details.get("format"), "string")
    return {}


def example_from_schema(schema, definitions, seen=None):
    """A request body example, omitting anything the server assigns."""
    seen = seen or set()

    if "$ref" in schema:
        ref_name = schema["$ref"].split("/")[-1]
        if ref_name in seen:
            # Self-referencing definition; stop rather than recurse forever.
            return {}
        return example_from_schema(
            definitions.get(ref_name, {}), definitions, seen | {ref_name}
        )

    if schema.get("type") == "array":
        return [example_from_schema(schema.get("items", {}), definitions, seen)]

    if "properties" not in schema:
        return {}

    properties = schema["properties"]
    example = OrderedDict()
    for name, details in properties.items():
        # Server-assigned: a client neither sends these nor should be shown them
        # in a request body.
        if details.get("readOnly"):
            continue
        # Swagger 2.0 cannot carry readOnly alongside a $ref, so a nested
        # read-only serializer (`category`, `uom`, `role`) comes through looking
        # writable. Throughout this API those pair with a `<name>_id` field that
        # is the actual write side, so the presence of that sibling is what
        # identifies the object as read-only.
        if set(details) == {"$ref"} and f"{name}_id" in properties:
            continue
        example[name] = example_for_property(details, definitions, seen)
    return example


def split_path(base_path, path):
    """Postman path segments, with :params in place of {params}."""
    segments = (base_path + path).strip("/").split("/")
    return [
        f":{segment[1:-1]}" if segment.startswith("{") else segment
        for segment in segments
    ]


def build_request(swagger, path, method, details):
    base_path = swagger.get("basePath", "")
    parameters = details.get("parameters", [])

    headers = []
    query = []
    path_variables = []
    body = None

    for parameter in parameters:
        location = parameter.get("in")
        if location == "body":
            body = {
                "mode": "raw",
                "raw": json.dumps(
                    example_from_schema(
                        parameter.get("schema", {}), swagger.get("definitions", {})
                    ),
                    indent=4,
                ),
                "options": {"raw": {"language": "json"}},
            }
            headers.append({"key": "Content-Type", "value": "application/json"})
        elif location == "header":
            value = (
                "{{organization_id}}"
                if parameter["name"] == "X-Organization"
                else "{{" + parameter["name"].lower().replace("-", "_") + "}}"
            )
            headers.append(
                {
                    "key": parameter["name"],
                    "value": value,
                    "description": parameter.get("description", ""),
                }
            )
        elif location == "query":
            query.append(
                {
                    "key": parameter["name"],
                    "value": "",
                    "description": parameter.get("description", ""),
                    # Off by default so a request runs cleanly as-is.
                    "disabled": True,
                }
            )
        elif location == "path":
            path_variables.append(
                {
                    "key": parameter["name"],
                    "value": "",
                    "description": parameter.get("description", ""),
                }
            )

    raw = "{{base_url}}" + base_path + path.replace("{", ":").replace("}", "")
    if query:
        raw += "?" + "&".join(f"{item['key']}=" for item in query)

    url = {
        "raw": raw,
        "host": ["{{base_url}}"],
        "path": split_path(base_path, path),
    }
    if query:
        url["query"] = query
    if path_variables:
        url["variable"] = path_variables

    request = {
        "method": method.upper(),
        "header": headers,
        "url": url,
        "description": details.get("description", ""),
    }
    if body:
        request["body"] = body

    # The webhooks are called by Safaricom and authenticate on the URL token, so
    # attaching the collection's bearer token to them would misrepresent them.
    if details.get("security") == []:
        request["auth"] = {"type": "noauth"}

    item = {
        "name": details.get("summary")
        or details.get("operationId")
        or f"{method.upper()} {path}",
        "request": request,
        "response": [],
    }

    if path.endswith("/auth/login/") or path == "/token/":
        item["event"] = [
            {"listen": "test", "script": {"type": "text/javascript", "exec": LOGIN_TEST_SCRIPT}}
        ]

    return item


def convert_swagger_to_postman(swagger_file=SWAGGER_FILE, postman_file=POSTMAN_FILE):
    with open(swagger_file) as handle:
        swagger = json.load(handle)

    collection = {
        "info": {
            "name": swagger["info"]["title"],
            "description": swagger["info"].get("description", ""),
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
        },
        "auth": {
            "type": "bearer",
            "bearer": [{"key": "token", "value": "{{access_token}}", "type": "string"}],
        },
        "variable": [
            {
                "key": "base_url",
                "value": "http://127.0.0.1:8000",
                "description": "Where the API is running.",
            },
            {
                "key": "organization_id",
                "value": "",
                "description": (
                    "The tenant, sent as X-Organization. Returned by "
                    "/api/organization/onboard/. Requests without it resolve to "
                    "no tenant and read back empty."
                ),
            },
            {
                "key": "access_token",
                "value": "",
                "description": "Set automatically by the login request.",
            },
            {"key": "refresh_token", "value": "", "description": "Set automatically by the login request."},
        ],
        "item": [],
    }

    folders = {}
    for path in sorted(swagger["paths"]):
        methods = swagger["paths"][path]
        for method, details in methods.items():
            if method == "parameters":
                continue

            tags = details.get("tags") or ["default"]
            folder_name = tags[0]
            if folder_name not in folders:
                folders[folder_name] = {"name": folder_name, "item": []}
                collection["item"].append(folders[folder_name])

            folders[folder_name]["item"].append(
                build_request(swagger, path, method, details)
            )

    collection["item"].sort(key=lambda folder: folder["name"])

    with open(postman_file, "w") as handle:
        json.dump(collection, handle, indent=4)

    request_count = sum(len(folder["item"]) for folder in collection["item"])
    print(
        f"Wrote {postman_file}: {len(collection['item'])} folders, "
        f"{request_count} requests."
    )


if __name__ == "__main__":
    convert_swagger_to_postman()
