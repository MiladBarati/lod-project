import json
import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

import lod.cli as cli
import lod.registry as registry
from lod.llm_openapi import LLMOpenAPIConverter

# Mock OpenAPI specification for testing
TEST_SPEC = {
    "openapi": "3.0.0",
    "info": {
        "title": "Test API",
        "version": "1.0.0",
        "description": "API description"
    },
    "paths": {
        "/users": {
            "get": {
                "summary": "Get Users",
                "description": "Retrieve users list",
                "parameters": [
                    {
                        "name": "limit",
                        "in": "query",
                        "required": False,
                        "schema": {
                            "type": "integer"
                        },
                        "description": "Max items"
                    }
                ],
                "responses": {
                    "200": {
                        "description": "Success",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "id": {
                                            "type": "integer"
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

TEST_SPEC_BREAKING = {
    "openapi": "3.0.0",
    "info": {
        "title": "Test API",
        "version": "1.0.1",
        "description": "API description"
    },
    "paths": {
        "/users": {
            "get": {
                "summary": "Get Users",
                "description": "Retrieve users list",
                "parameters": [],  # Removed parameter 'limit' (breaking change!)
                "responses": {
                    "200": {
                        "description": "Success",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "id": {
                                            "type": "integer"
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

class TestModelAdapters(unittest.TestCase):

    def test_generic_formatter(self):
        """Verify the generic/default formatter compiles correctly."""
        converter = LLMOpenAPIConverter(TEST_SPEC)
        output = converter.convert()
        self.assertIn("# Test API (v1.0.0)", output)
        self.assertIn("GET /users \"Get Users\"", output)
        self.assertIn("limit: integer", output)

    def test_claude_xml_formatter(self):
        """Verify the Claude XML formatter generates structured XML."""
        converter = LLMOpenAPIConverter(TEST_SPEC, model="claude")
        output = converter.convert()
        self.assertIn('<api title="Test API" version="1.0.0">', output)
        self.assertIn('<path>GET /users</path>', output)
        self.assertIn('<query name="limit" type="integer" required="false">Max items</query>', output)
        self.assertIn('</api>', output)

    def test_gpt_yaml_formatter(self):
        """Verify the GPT YAML formatter generates clean YAML."""
        converter = LLMOpenAPIConverter(TEST_SPEC, model="gpt")
        output = converter.convert()
        self.assertIn("info:", output)
        self.assertIn("GET /users:", output)
        self.assertIn("limit: integer # Max items", output)

    def test_gemini_typescript_formatter(self):
        """Verify the Gemini formatter generates TypeScript types and functions."""
        converter = LLMOpenAPIConverter(TEST_SPEC, model="gemini")
        output = converter.convert()
        self.assertIn("interface GetUsersParams {", output)
        self.assertIn("function getUsers(params: GetUsersParams): Promise<GetUsersResponse>;", output)

    def test_flat_definitions(self):
        """Verify formatters generate flat definitions and reference them by key."""
        spec_with_refs = {
            "openapi": "3.0.0",
            "info": {"title": "Ref API", "version": "1.0.0"},
            "components": {
                "schemas": {
                    "User": {
                        "type": "object",
                        "properties": {
                            "username": {"type": "string"}
                        }
                    }
                }
            },
            "paths": {
                "/user": {
                    "post": {
                        "requestBody": {
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "$ref": "#/components/schemas/User"
                                    }
                                }
                            }
                        },
                        "responses": {
                            "200": {
                                "description": "success",
                                "content": {
                                    "application/json": {
                                        "schema": {
                                            "$ref": "#/components/schemas/User"
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }

        # 1. Generic Formatter
        generic_out = LLMOpenAPIConverter(spec_with_refs).convert()
        self.assertIn("definitions:", generic_out)
        self.assertIn("User: object", generic_out)
        self.assertIn("application/json: $User", generic_out)

        # 2. GPT Formatter
        gpt_out = LLMOpenAPIConverter(spec_with_refs, model="gpt").convert()
        self.assertIn("definitions:", gpt_out)
        self.assertIn("User: object", gpt_out)
        self.assertIn("application/json: $User", gpt_out)

        # 3. Claude Formatter
        claude_out = LLMOpenAPIConverter(spec_with_refs, model="claude").convert()
        self.assertIn("<definitions>", claude_out)
        self.assertIn('<property name="User" type="object">', claude_out)
        self.assertIn('ref="User"', claude_out)

        # 4. Gemini Formatter
        gemini_out = LLMOpenAPIConverter(spec_with_refs, model="gemini").convert()
        self.assertIn("interface User {", gemini_out)
        self.assertIn("type PostUserRequest = User;", gemini_out)
        self.assertIn("type PostUserResponse = User;", gemini_out)


class TestRegistry(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.input_file = os.path.join(self.temp_dir, "input.json")
        with open(self.input_file, "w", encoding="utf-8") as f:
            json.dump(TEST_SPEC, f)

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_register_and_get(self):
        """Test registering a spec version and fetching it back."""
        dest = registry.register_spec(self.input_file, "test-api", "v1.0.0", registry_dir=self.temp_dir)
        self.assertTrue(os.path.exists(dest))
        self.assertTrue(dest.endswith("test-api/v1.0.0.json"))

        fetched = registry.get_spec("test-api", "v1.0.0", registry_dir=self.temp_dir)
        self.assertEqual(fetched["info"]["title"], "Test API")

    def test_resolve_registry_uri(self):
        """Test resolving registry:// URIs."""
        registry.register_spec(self.input_file, "test-api", "v1.0.0", registry_dir=self.temp_dir)
        resolved = registry.resolve_registry_uri("registry://test-api:v1.0.0", registry_dir=self.temp_dir)
        self.assertEqual(resolved["info"]["title"], "Test API")

        with self.assertRaises(ValueError):
            registry.resolve_registry_uri("registry://test-api", registry_dir=self.temp_dir)

        with self.assertRaises(FileNotFoundError):
            registry.resolve_registry_uri("registry://test-api:v2.0.0", registry_dir=self.temp_dir)


class TestCLI(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.spec_file = os.path.join(self.temp_dir, "spec.json")
        self.breaking_spec_file = os.path.join(self.temp_dir, "breaking.json")
        self.output_file = os.path.join(self.temp_dir, "output.md")

        with open(self.spec_file, "w", encoding="utf-8") as f:
            json.dump(TEST_SPEC, f)
        with open(self.breaking_spec_file, "w", encoding="utf-8") as f:
            json.dump(TEST_SPEC_BREAKING, f)

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_cli_compile(self):
        """Test lod compile subcommand."""
        args = ["lod", "compile", "-i", self.spec_file, "-o", self.output_file]
        with patch("sys.argv", args):
            cli.main()
        self.assertTrue(os.path.exists(self.output_file))
        with open(self.output_file, "r") as f:
            content = f.read()
        self.assertIn("# Test API (v1.0.0)", content)

    def test_cli_check_clean(self):
        """Test lod check with no breaking changes."""
        args = ["lod", "check", "-i", self.spec_file, "-b", self.spec_file]
        with patch("sys.argv", args):
            with self.assertRaises(SystemExit) as cm:
                cli.main()
        self.assertEqual(cm.exception.code, 0)

    def test_cli_check_breaking(self):
        """Test lod check with breaking drift."""
        args = ["lod", "check", "-i", self.breaking_spec_file, "-b", self.spec_file]
        with patch("sys.argv", args):
            with self.assertRaises(SystemExit) as cm:
                cli.main()
        self.assertEqual(cm.exception.code, 1)

    def test_cli_check_error_loading(self):
        """Test lod check with baseline loading failure."""
        args = ["lod", "check", "-i", self.spec_file, "-b", "non-existent-file.json"]
        with patch("sys.argv", args):
            with self.assertRaises(SystemExit) as cm:
                cli.main()
        self.assertEqual(cm.exception.code, 2)

    @patch("lod.cli.register_spec")
    def test_cli_registry_register(self, mock_register):
        """Test registry register command routing."""
        args = ["lod", "registry", "register", "-i", self.spec_file, "--spec-id", "petstore", "--tag", "v1.0.0"]
        with patch("sys.argv", args):
            with self.assertRaises(SystemExit) as cm:
                cli.main()
        self.assertEqual(cm.exception.code, 0)
        mock_register.assert_called_once_with(self.spec_file, "petstore", "v1.0.0")

if __name__ == "__main__":
    unittest.main()
