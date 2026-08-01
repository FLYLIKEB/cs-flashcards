from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parent.parent
DEPLOY_SCRIPT = ROOT / "scripts" / "deploy_lightsail_flashcards.sh"
DEPLOY_WORKFLOW = ROOT / ".github" / "workflows" / "deploy-lightsail.yml"
README = ROOT / "README.md"


class DeployRuntimeContractTests(unittest.TestCase):
    def test_deploy_script_validates_local_progress_sqlite_and_remote_health(self):
        script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
        self.assertIn('verify_sqlite_has_cards "$ROOT_DIR/state/progress.sqlite" "로컬"', script)
        self.assertIn('Runtime progress DB is not healthy', script)
        self.assertIn('curl --fail --show-error --silent', script)
        self.assertNotIn('api/health" || true', script)

    def test_deploy_script_uses_environment_file_for_runtime_secrets(self):
        script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
        self.assertIn('EnvironmentFile=$RUNTIME_ENV_PATH', script)
        self.assertNotIn('Environment=CS_FLASHCARDS_PASSWORD=', script)
        self.assertNotIn('Environment=CS_FLASHCARDS_WIKI_GITHUB_TOKEN=', script)
        self.assertNotIn('Environment=OPENAI_API_KEY=', script)
        self.assertIn('/tmp/cs-flashcards-runtime.env', script)
        self.assertNotIn('source "$RUNTIME_ENV_PATH"', script)
        self.assertIn('RUNTIME_BASIC_AUTH_HEADER', script)

    def test_deploy_workflow_still_verifies_health_endpoint(self):
        workflow = DEPLOY_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn('./scripts/deploy_lightsail_flashcards.sh', workflow)
        self.assertIn('https://cs.chamung.com/api/health', workflow)

    def test_readme_documents_preserved_remote_sqlite_contract(self):
        readme = README.read_text(encoding="utf-8")
        self.assertIn('일반 배포는 원격 `state/progress.sqlite`를 **보존**합니다.', readme)
        self.assertIn('content_card_count', readme)


if __name__ == '__main__':
    unittest.main()
