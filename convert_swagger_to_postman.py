import json

def convert_swagger_to_postman(swagger_file, postman_file):
    with open(swagger_file, 'r') as f:
        swagger_data = json.load(f)

    postman_collection = {
        "info": {
            "name": swagger_data["info"]["title"],
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"
        },
        "item": []
    }

    for path, methods in swagger_data["paths"].items():
        for method, details in methods.items():
            if method == "parameters":
                continue

            folder_name = details["tags"][0] if "tags" in details and details["tags"] else "default"
            folder = next((item for item in postman_collection["item"] if item["name"] == folder_name), None)
            if not folder:
                folder = {
                    "name": folder_name,
                    "item": []
                }
                postman_collection["item"].append(folder)

            request = {
                "name": details.get("summary") or details.get("operationId") or path,
                "request": {
                    "method": method.upper(),
                    "header": [],
                    "url": {
                        "raw": f"{{{{base_url}}}}{swagger_data.get('basePath', '')}{path}",
                        "host": [
                            "{{base_url}}"
                        ],
                        "path": (swagger_data.get('basePath', '') + path).strip('/').split('/')
                    }
                },
                "response": []
            }

            if "parameters" in details:
                for param in details["parameters"]:
                    if param["in"] == "body":
                        request["request"]["body"] = {
                            "mode": "raw",
                            "raw": json.dumps(get_example_from_schema(param["schema"], swagger_data.get("definitions", {})), indent=4),
                            "options": {
                                "raw": {
                                    "language": "json"
                                }
                            }
                        }

            folder["item"].append(request)

    with open(postman_file, 'w') as f:
        json.dump(postman_collection, f, indent=4)

def get_example_from_schema(schema, definitions):
    if "$ref" in schema:
        ref_name = schema["$ref"].split("/")[-1]
        return get_example_from_schema(definitions[ref_name], definitions)
    if "properties" in schema:
        example = {}
        for prop_name, prop_details in schema["properties"].items():
            if "example" in prop_details:
                example[prop_name] = prop_details["example"]
            elif "type" in prop_details:
                if prop_details["type"] == "string":
                    example[prop_name] = "string"
                elif prop_details["type"] == "integer":
                    example[prop_name] = 0
                elif prop_details["type"] == "boolean":
                    example[prop_name] = False
                else:
                    example[prop_name] = {}
            else:
                example[prop_name] = {}
        return example
    return {}

if __name__ == '__main__':
    convert_swagger_to_postman('swagger.json', 'blendy-suite-v1.json')
