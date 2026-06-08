import io
import json
import os
import shutil
import tempfile
import unittest
import urllib.error
from unittest.mock import MagicMock, patch

import lod.cli as cli
from lod.remediation import GithubRemediator


class TestGithubRemediator(unittest.TestCase):
    def setUp(self):
        self.remediator = GithubRemediator(
            repo="test-owner/test-repo",
            token="test-token",
            target_file="docs/api.md",
            base_branch="main"
        )
        self.mock_spec = {
            "openapi": "3.0.0",
            "info": {"title": "Test Spec", "version": "1.0.0"},
            "paths": {}
        }

    @patch("urllib.request.urlopen")
    def test_get_base_sha(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "object": {"sha": "abc123sha"}
        }).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        sha = self.remediator.get_base_sha()
        self.assertEqual(sha, "abc123sha")
        mock_urlopen.assert_called_once()
        req = mock_urlopen.call_args[0][0]
        self.assertEqual(req.full_url, "https://api.github.com/repos/test-owner/test-repo/git/ref/heads/main")
        self.assertEqual(req.headers.get("Authorization"), "token test-token")

    @patch("urllib.request.urlopen")
    def test_create_branch(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = b"{}"
        mock_urlopen.return_value.__enter__.return_value = mock_response

        self.remediator.create_branch("new-branch", "abc123sha")
        mock_urlopen.assert_called_once()
        req = mock_urlopen.call_args[0][0]
        self.assertEqual(req.method, "POST")
        self.assertEqual(req.full_url, "https://api.github.com/repos/test-owner/test-repo/git/refs")
        body = json.loads(req.data.decode("utf-8"))
        self.assertEqual(body["ref"], "refs/heads/new-branch")
        self.assertEqual(body["sha"], "abc123sha")

    @patch("urllib.request.urlopen")
    def test_get_file_sha_exists(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({"sha": "filesha456"}).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        sha = self.remediator.get_file_sha("new-branch")
        self.assertEqual(sha, "filesha456")
        req = mock_urlopen.call_args[0][0]
        self.assertEqual(req.full_url, "https://api.github.com/repos/test-owner/test-repo/contents/docs/api.md?ref=new-branch")

    @patch("urllib.request.urlopen")
    def test_get_file_sha_not_found(self, mock_urlopen):
        # HTTP Error 404 Not Found
        mock_error = urllib.error.HTTPError(
            url="https://api.github.com/...",
            code=404,
            msg="Not Found",
            hdrs=None,
            fp=io.BytesIO(b'{"message": "Not Found"}')
        )
        mock_urlopen.side_effect = mock_error

        sha = self.remediator.get_file_sha("new-branch")
        self.assertIsNone(sha)

    @patch("urllib.request.urlopen")
    def test_commit_file(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = b"{}"
        mock_urlopen.return_value.__enter__.return_value = mock_response

        self.remediator.commit_file("new LOM spec content", "new-branch", file_sha="filesha456")
        mock_urlopen.assert_called_once()
        req = mock_urlopen.call_args[0][0]
        self.assertEqual(req.method, "PUT")
        self.assertEqual(req.full_url, "https://api.github.com/repos/test-owner/test-repo/contents/docs/api.md")
        body = json.loads(req.data.decode("utf-8"))
        self.assertEqual(body["branch"], "new-branch")
        self.assertEqual(body["sha"], "filesha456")
        # base64 decode check
        import base64
        decoded = base64.b64decode(body["content"].encode("utf-8")).decode("utf-8")
        self.assertEqual(decoded, "new LOM spec content")

    @patch("urllib.request.urlopen")
    def test_create_pull_request(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "html_url": "https://github.com/test-owner/test-repo/pull/42",
            "number": 42
        }).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        pr_info = self.remediator.create_pull_request("new-branch")
        self.assertEqual(pr_info["html_url"], "https://github.com/test-owner/test-repo/pull/42")
        self.assertEqual(pr_info["number"], 42)
        req = mock_urlopen.call_args[0][0]
        self.assertEqual(req.method, "POST")
        self.assertEqual(req.full_url, "https://api.github.com/repos/test-owner/test-repo/pulls")

    @patch("lod.remediation.GithubRemediator.get_base_sha")
    @patch("lod.remediation.GithubRemediator.create_branch")
    @patch("lod.remediation.GithubRemediator.get_file_sha")
    @patch("lod.remediation.GithubRemediator.commit_file")
    @patch("lod.remediation.GithubRemediator.create_pull_request")
    def test_remediate_flow(self, mock_pr, mock_commit, mock_file_sha, mock_branch, mock_base_sha):
        mock_base_sha.return_value = "base123sha"
        mock_file_sha.return_value = "file456sha"
        mock_pr.return_value = {
            "html_url": "https://github.com/test-owner/test-repo/pull/101",
            "number": 101
        }

        result = self.remediator.remediate(self.mock_spec, model="gpt")

        mock_base_sha.assert_called_once()
        mock_branch.assert_called_once()
        mock_file_sha.assert_called_once()
        mock_commit.assert_called_once()
        mock_pr.assert_called_once()

        self.assertEqual(result["pr_number"], 101)
        self.assertEqual(result["pr_url"], "https://github.com/test-owner/test-repo/pull/101")
        self.assertTrue(result["branch"].startswith("lod-remediation-"))

    @patch("subprocess.run")
    @patch("lod.remediation.GithubRemediator.get_base_sha")
    @patch("lod.remediation.GithubRemediator.create_branch")
    @patch("lod.remediation.GithubRemediator.get_file_sha")
    @patch("lod.remediation.GithubRemediator.commit_file")
    @patch("lod.remediation.GithubRemediator.create_pull_request")
    def test_remediate_verification_success(self, mock_pr, mock_commit, mock_file_sha, mock_branch, mock_base_sha, mock_run):
        mock_base_sha.return_value = "base123sha"
        mock_file_sha.return_value = "file456sha"
        mock_pr.return_value = {"html_url": "https://github.com/test-owner/test-repo/pull/101", "number": 101}

        mock_subprocess_result = MagicMock()
        mock_subprocess_result.returncode = 0
        mock_subprocess_result.stdout = "test passed"
        mock_subprocess_result.stderr = ""
        mock_run.return_value = mock_subprocess_result

        result = self.remediator.remediate(self.mock_spec, model="gpt", verify_cmd="pytest tests")

        mock_run.assert_called_once_with("pytest tests", shell=True, capture_output=True, text=True)
        mock_pr.assert_called_once_with("lod-remediation-" + result["branch"].split("-")[-1], verification_status={
            "success": True,
            "returncode": 0,
            "logs": "--- stdout ---\ntest passed\n--- stderr ---\n",
            "cmd": "pytest tests"
        })
        self.assertEqual(result["pr_number"], 101)

    @patch("subprocess.run")
    @patch("lod.remediation.GithubRemediator.get_base_sha")
    @patch("lod.remediation.GithubRemediator.create_branch")
    @patch("lod.remediation.GithubRemediator.get_file_sha")
    @patch("lod.remediation.GithubRemediator.commit_file")
    @patch("lod.remediation.GithubRemediator.create_pull_request")
    def test_remediate_verification_failure_abort(self, mock_pr, mock_commit, mock_file_sha, mock_branch, mock_base_sha, mock_run):
        mock_subprocess_result = MagicMock()
        mock_subprocess_result.returncode = 1
        mock_subprocess_result.stdout = ""
        mock_subprocess_result.stderr = "test failed"
        mock_run.return_value = mock_subprocess_result

        with self.assertRaises(ValueError) as context:
            self.remediator.remediate(self.mock_spec, model="gpt", verify_cmd="pytest tests")

        self.assertIn("Verification failed with exit code 1", str(context.exception))
        mock_commit.assert_not_called()
        mock_pr.assert_not_called()

    @patch("subprocess.run")
    @patch("lod.remediation.GithubRemediator.get_base_sha")
    @patch("lod.remediation.GithubRemediator.create_branch")
    @patch("lod.remediation.GithubRemediator.get_file_sha")
    @patch("lod.remediation.GithubRemediator.commit_file")
    @patch("lod.remediation.GithubRemediator.create_pull_request")
    def test_remediate_verification_failure_allow_override(self, mock_pr, mock_commit, mock_file_sha, mock_branch, mock_base_sha, mock_run):
        mock_base_sha.return_value = "base123sha"
        mock_file_sha.return_value = "file456sha"
        mock_pr.return_value = {"html_url": "https://github.com/test-owner/test-repo/pull/101", "number": 101}

        mock_subprocess_result = MagicMock()
        mock_subprocess_result.returncode = 1
        mock_subprocess_result.stdout = ""
        mock_subprocess_result.stderr = "test failed"
        mock_run.return_value = mock_subprocess_result

        result = self.remediator.remediate(self.mock_spec, model="gpt", verify_cmd="pytest tests", allow_failed_verification=True)

        mock_commit.assert_called_once()
        mock_pr.assert_called_once_with("lod-remediation-" + result["branch"].split("-")[-1], verification_status={
            "success": False,
            "returncode": 1,
            "logs": "--- stdout ---\n\n--- stderr ---\ntest failed",
            "cmd": "pytest tests"
        })
        self.assertEqual(result["pr_number"], 101)


class TestCLIRemediationIntegration(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.base_spec_file = os.path.join(self.temp_dir, "base.json")
        self.current_spec_file = os.path.join(self.temp_dir, "current.json")

        # Test OpenAPI spec with a parameter
        self.base_spec = {
            "openapi": "3.0.0",
            "info": {"title": "Test API", "version": "1.0.0"},
            "paths": {
                "/users": {
                    "get": {
                        "parameters": [
                            {"name": "limit", "in": "query", "required": False, "schema": {"type": "integer"}}
                        ],
                        "responses": {"200": {"description": "success"}}
                    }
                }
            }
        }
        # Current spec has parameter deleted (breaking change!)
        self.current_spec = {
            "openapi": "3.0.0",
            "info": {"title": "Test API", "version": "1.0.0"},
            "paths": {
                "/users": {
                    "get": {
                        "parameters": [],
                        "responses": {"200": {"description": "success"}}
                    }
                }
            }
        }

        with open(self.base_spec_file, "w", encoding="utf-8") as f:
            json.dump(self.base_spec, f)
        with open(self.current_spec_file, "w", encoding="utf-8") as f:
            json.dump(self.current_spec, f)

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    @patch("lod.cli.GithubRemediator")
    def test_cli_remediation_trigger(self, mock_remediator_class):
        mock_remediator_instance = MagicMock()
        mock_remediator_class.return_value = mock_remediator_instance
        mock_remediator_instance.remediate.return_value = {
            "branch": "lod-remediation-9999",
            "pr_url": "https://github.com/owner/repo/pull/9999",
            "pr_number": 9999
        }

        # Test using the new subcommand-based CLI
        args = [
            "lod", "remediate",
            "-i", self.current_spec_file,
            "-b", self.base_spec_file,
            "--git-repo", "owner/repo",
            "--git-token", "token123",
            "--target-file", "docs/api.md",
            "--model", "gpt"
        ]

        with patch("sys.argv", args):
            cli.main()

        # Verify the remediator was correctly initialized and invoked
        mock_remediator_class.assert_called_once_with(
            repo="owner/repo",
            token="token123",
            target_file="docs/api.md"
        )
        mock_remediator_instance.remediate.assert_called_once()
        args_passed = mock_remediator_instance.remediate.call_args[0][0]
        self.assertEqual(args_passed["info"]["title"], "Test API")
        self.assertEqual(mock_remediator_instance.remediate.call_args[1]["model"], "gpt")

    @patch("lod.cli.GithubRemediator")
    def test_cli_remediation_trigger_with_verification(self, mock_remediator_class):
        mock_remediator_instance = MagicMock()
        mock_remediator_class.return_value = mock_remediator_instance
        mock_remediator_instance.remediate.return_value = {
            "branch": "lod-remediation-9999",
            "pr_url": "https://github.com/owner/repo/pull/9999",
            "pr_number": 9999
        }

        args = [
            "lod", "remediate",
            "-i", self.current_spec_file,
            "-b", self.base_spec_file,
            "--git-repo", "owner/repo",
            "--git-token", "token123",
            "--target-file", "docs/api.md",
            "--model", "gpt",
            "--verify-cmd", "pytest tests",
            "--allow-failed-verification"
        ]

        with patch("sys.argv", args):
            cli.main()

        mock_remediator_class.assert_called_once_with(
            repo="owner/repo",
            token="token123",
            target_file="docs/api.md"
        )
        mock_remediator_instance.remediate.assert_called_once_with(
            mock_remediator_instance.remediate.call_args[0][0],
            model="gpt",
            verify_cmd="pytest tests",
            allow_failed_verification=True
        )


if __name__ == "__main__":
    unittest.main()
