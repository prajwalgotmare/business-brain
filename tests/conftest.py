import os

os.environ["APP_ENV"] = "test"
os.environ["AUTH_MODE"] = "mock"
os.environ["GROQ_API_KEY"] = "test-groq-key"
os.environ["LANGFUSE_ENABLED"] = "false"
