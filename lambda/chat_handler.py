"""AWS Lambda handler for the Agent Chat API (Cerebras + governance intercept testing)."""

from mangum import Mangum

from shared.config.settings import reload_settings

reload_settings()

from backend.api.chat_app import app  # noqa: E402

_handler = Mangum(app, lifespan="auto")


def handler(event, context):
    return _handler(event, context)
