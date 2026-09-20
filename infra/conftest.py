import sys
from pathlib import Path

# So `from stacks.chat_with_your_docs_stack import ...` resolves regardless of the
# working directory pytest is invoked from (app.py relies on the same cwd-relative
# import, which normally works there because cdk always runs it from infra/).
sys.path.insert(0, str(Path(__file__).resolve().parent))
