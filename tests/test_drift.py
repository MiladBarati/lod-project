import unittest
import copy
from lod.drift import compare_specs

class TestSchemaDrift(unittest.TestCase):
    def setUp(self):
        self.base_spec = {
            "openapi": "3.0.0",
            "info": {"title": "Test API", "version": "1.0.0"},
            "paths": {
                "/users": {
                    "get": {
                        "summary": "Get Users",
                        "parameters": [
                            {
                                "name": "limit",
                                "in": "query",
                                "required": False,
                                "schema": {"type": "integer"}
                            },
                            {
                                "name": "role",
                                "in": "query",
                                "required": True,
                                "schema": {"type": "string"}
                            }
                        ],
                        "responses": {"200": {"description": "success"}}
                    },
                    "post": {
                        "summary": "Create User",
                        "requestBody": {
                            "required": True,
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "required": ["username"],
                                        "properties": {
                                            "username": {"type": "string"},
                                            "email": {"type": "string"}
                                        }
                                    }
                                }
                            }
                        },
                        "responses": {"201": {"description": "created"}}
                    }
                }
            }
        }

    def test_no_changes(self):
        new_spec = copy.deepcopy(self.base_spec)
        report = compare_specs(self.base_spec, new_spec)
        self.assertFalse(report["is_breaking"])
        self.assertEqual(len(report["breaking_changes"]), 0)
        self.assertEqual(len(report["non_breaking_changes"]), 0)

    def test_deleted_endpoint(self):
        new_spec = copy.deepcopy(self.base_spec)
        del new_spec["paths"]["/users"]["post"]
        
        report = compare_specs(self.base_spec, new_spec)
        self.assertTrue(report["is_breaking"])
        self.assertTrue(any("Deleted endpoint" in c for c in report["breaking_changes"]))

    def test_added_endpoint(self):
        new_spec = copy.deepcopy(self.base_spec)
        new_spec["paths"]["/users"]["put"] = {
            "summary": "Update User",
            "responses": {"200": {"description": "updated"}}
        }
        
        report = compare_specs(self.base_spec, new_spec)
        self.assertFalse(report["is_breaking"])
        self.assertTrue(any("Added endpoint: PUT /users" in c for c in report["non_breaking_changes"]))

    def test_deleted_parameter(self):
        new_spec = copy.deepcopy(self.base_spec)
        # Delete parameter 'limit' (index 0)
        new_spec["paths"]["/users"]["get"]["parameters"].pop(0)

        report = compare_specs(self.base_spec, new_spec)
        self.assertTrue(report["is_breaking"])
        self.assertTrue(any("Deleted parameter `limit`" in c for c in report["breaking_changes"]))

    def test_added_optional_parameter(self):
        new_spec = copy.deepcopy(self.base_spec)
        new_spec["paths"]["/users"]["get"]["parameters"].append({
            "name": "offset",
            "in": "query",
            "required": False,
            "schema": {"type": "integer"}
        })

        report = compare_specs(self.base_spec, new_spec)
        self.assertFalse(report["is_breaking"])
        self.assertTrue(any("Added optional parameter `offset`" in c for c in report["non_breaking_changes"]))

    def test_added_required_parameter(self):
        new_spec = copy.deepcopy(self.base_spec)
        new_spec["paths"]["/users"]["get"]["parameters"].append({
            "name": "token",
            "in": "query",
            "required": True,
            "schema": {"type": "string"}
        })

        report = compare_specs(self.base_spec, new_spec)
        self.assertTrue(report["is_breaking"])
        self.assertTrue(any("Added required parameter `token`" in c for c in report["breaking_changes"]))

    def test_parameter_type_changed(self):
        new_spec = copy.deepcopy(self.base_spec)
        # Change 'limit' type to string
        new_spec["paths"]["/users"]["get"]["parameters"][0]["schema"]["type"] = "string"

        report = compare_specs(self.base_spec, new_spec)
        self.assertTrue(report["is_breaking"])
        self.assertTrue(any("type changed" in c for c in report["breaking_changes"]))

    def test_parameter_optional_to_required(self):
        new_spec = copy.deepcopy(self.base_spec)
        # Change 'limit' required to True
        new_spec["paths"]["/users"]["get"]["parameters"][0]["required"] = True

        report = compare_specs(self.base_spec, new_spec)
        self.assertTrue(report["is_breaking"])
        self.assertTrue(any("changed from optional to required" in c for c in report["breaking_changes"]))

    def test_request_body_field_deleted(self):
        new_spec = copy.deepcopy(self.base_spec)
        del new_spec["paths"]["/users"]["post"]["requestBody"]["content"]["application/json"]["schema"]["properties"]["email"]

        report = compare_specs(self.base_spec, new_spec)
        self.assertTrue(report["is_breaking"])
        self.assertTrue(any("Request body field `email` deleted" in c for c in report["breaking_changes"]))

    def test_request_body_field_type_changed(self):
        new_spec = copy.deepcopy(self.base_spec)
        new_spec["paths"]["/users"]["post"]["requestBody"]["content"]["application/json"]["schema"]["properties"]["email"]["type"] = "integer"

        report = compare_specs(self.base_spec, new_spec)
        self.assertTrue(report["is_breaking"])
        self.assertTrue(any("type changed from `string` to `integer`" in c for c in report["breaking_changes"]))

if __name__ == "__main__":
    unittest.main()
