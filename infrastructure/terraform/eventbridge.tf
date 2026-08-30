resource "aws_cloudwatch_event_bus" "governance_bus" {
  name = local.eventbridge_bus_name
}

# --- Governance SLA sweep (PS-4.2 bonus) ---
# Periodically invokes the API Lambda to auto-escalate agents whose
# under-review SLA (default 48h) has elapsed.
resource "aws_cloudwatch_event_rule" "governance_sla_sweep" {
  name                = "${local.prefix}-governance-sla-sweep"
  description         = "Periodic governance SLA breach check and auto-escalation"
  schedule_expression = "rate(15 minutes)"
}

resource "aws_cloudwatch_event_target" "governance_sla_sweep" {
  rule      = aws_cloudwatch_event_rule.governance_sla_sweep.name
  target_id = "governance-sla-lambda"
  arn       = aws_lambda_function.api.arn
  input     = jsonencode({ task = "sla-check" })
}

resource "aws_lambda_permission" "allow_eventbridge_sla" {
  statement_id  = "AllowSLASweepInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.api.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.governance_sla_sweep.arn
}
