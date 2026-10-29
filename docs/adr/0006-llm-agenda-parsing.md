# ADR 0006: LLM agenda parsing

Status: accepted

## Context
Agendas usually come as an email or a chat message, not as a form. I added "Paste an agenda": the user pastes text, an LLM turns it into a structured agenda, the form is pre-filled, the user checks it and presses Save.

Constraints: no NAT and no VPC endpoints (they cost money when idle), every call costs tokens, and the pasted text comes from outside, so it can contain instructions.

## Decision
- Model: Claude on Amazon Bedrock (`anthropic.claude-opus-5-5`, set in `PARSER_MODEL`, so it can be swapped for Haiku without code changes). No API keys, the Lambda role is allowed to call it.
- The parser is its own Lambda with a function URL, outside the VPC. It gets text and returns JSON, it does not need the database, so it reaches Bedrock over the internet and costs $0 when nobody uses it.
- The model never writes. It only suggests. Save goes through the normal API (`POST /api/meetings/{id}/agenda`) with its usual validation.
- The answer is a tool call checked by a pydantic schema. If it is invalid, the model gets one retry with the error, then the user gets a clear error and can type the agenda by hand.
- The function URL is public but every call needs a Cognito ID token (checked in the handler), text is limited to 10,000 characters, and a $5 monthly budget alarm sends me an email.
- The save request also stores the model's suggestion, model and prompt version (`ai_suggestion`). The difference between suggestion and saved agenda is the quality signal.

## Alternatives
- **Bedrock from the API through a VPC endpoint**: works, but an interface endpoint is about $7.30 a month and the API would need the permission to call the model. Lost on idle cost.
- **Claude API directly instead of Bedrock**: needs an API key to store and rotate, and the bill is outside AWS. Lost on secrets and cost control.
- **Regular expressions**: free and fast, but they break on every new wording and cannot resolve "Monday" or "by Friday". Lost on quality.

## Consequences
- One parse costs roughly $0.016 with Opus and $0.0004 with Haiku (estimate, real numbers are in the CloudWatch log line: model, prompt version, tokens, latency, cost).
- Logged for every parse: user, model, prompt version, input and output tokens, latency, cost.
- Bedrock down or throttled: the user sees "service is busy" and types the agenda by hand. Everything else in Spry keeps working because the parser is separate from the API.
- Prompt injection can at most change the suggested text, the user sees it before Save.
