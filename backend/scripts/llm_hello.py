"""make llm-hello: first call to Claude on Bedrock from the laptop."""

import os

from anthropic import AnthropicBedrockMantle

client = AnthropicBedrockMantle(aws_region=os.getenv("BEDROCK_REGION", "us-east-1"))
msg = client.messages.create(
    model=os.getenv("PARSER_MODEL", "anthropic.claude-opus-5-5"),
    max_tokens=1024,
    output_config={"effort": "low"},
    messages=[{"role": "user", "content": "In one sentence: what is an ISO week?"}],
)
print(next(b.text for b in msg.content if b.type == "text"))
print(msg.stop_reason, msg.usage.input_tokens, msg.usage.output_tokens)
