resource "aws_apigatewayv2_api" "waf_websocket" {
  name                       = "${local.prefix}-waf-stream"
  protocol_type              = "WEBSOCKET"
  route_selection_expression = "$request.body.action"
}

resource "aws_apigatewayv2_integration" "waf_ws_integration" {
  api_id           = aws_apigatewayv2_api.waf_websocket.id
  integration_type = "AWS_PROXY"
  integration_uri  = aws_lambda_function.waf_ws.invoke_arn
}

resource "aws_apigatewayv2_route" "connect_route" {
  api_id    = aws_apigatewayv2_api.waf_websocket.id
  route_key = "$connect"
  target    = "integrations/${aws_apigatewayv2_integration.waf_ws_integration.id}"
}

resource "aws_apigatewayv2_route" "disconnect_route" {
  api_id    = aws_apigatewayv2_api.waf_websocket.id
  route_key = "$disconnect"
  target    = "integrations/${aws_apigatewayv2_integration.waf_ws_integration.id}"
}

resource "aws_apigatewayv2_route" "default_route" {
  api_id    = aws_apigatewayv2_api.waf_websocket.id
  route_key = "$default"
  target    = "integrations/${aws_apigatewayv2_integration.waf_ws_integration.id}"
}

resource "aws_apigatewayv2_stage" "waf_ws_stage" {
  api_id      = aws_apigatewayv2_api.waf_websocket.id
  name        = var.waf_websocket_stage
  auto_deploy = true
  
  depends_on = [
    aws_apigatewayv2_route.connect_route,
    aws_apigatewayv2_route.disconnect_route,
    aws_apigatewayv2_route.default_route
  ]
}

resource "aws_lambda_permission" "apigw_invoke_waf_ws" {
  statement_id  = "AllowExecutionFromAPIGateway"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.waf_ws.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.waf_websocket.execution_arn}/*/*"
}

# --- REST HTTP API ---
resource "aws_apigatewayv2_api" "rest_api" {
  name          = "${local.prefix}-rest-api"
  protocol_type = "HTTP"

  cors_configuration {
    allow_credentials = true
    allow_origins = [
      "http://localhost:5173",
      "http://localhost:5174",
      "http://localhost:3000",
      "https://${aws_cloudfront_distribution.frontend_cdn.domain_name}"
    ]
    allow_methods = ["*"]
    allow_headers = ["*"]
    max_age       = 86400
  }
}

resource "aws_apigatewayv2_stage" "rest_api_stage" {
  api_id      = aws_apigatewayv2_api.rest_api.id
  name        = "$default"
  auto_deploy = true
}

resource "aws_apigatewayv2_integration" "rest_api_integration" {
  api_id             = aws_apigatewayv2_api.rest_api.id
  integration_type   = "AWS_PROXY"
  integration_uri    = aws_lambda_function.api.invoke_arn
  integration_method = "POST"
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_integration" "chat_integration" {
  api_id                 = aws_apigatewayv2_api.rest_api.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.chat.invoke_arn
  integration_method     = "POST"
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "chat_post" {
  api_id    = aws_apigatewayv2_api.rest_api.id
  route_key = "POST /v1/chat"
  target    = "integrations/${aws_apigatewayv2_integration.chat_integration.id}"
}

resource "aws_apigatewayv2_route" "chat_suggestions" {
  api_id    = aws_apigatewayv2_api.rest_api.id
  route_key = "GET /v1/chat/suggestions"
  target    = "integrations/${aws_apigatewayv2_integration.chat_integration.id}"
}

resource "aws_apigatewayv2_route" "chat_llm_status" {
  api_id    = aws_apigatewayv2_api.rest_api.id
  route_key = "GET /v1/chat/llm-status"
  target    = "integrations/${aws_apigatewayv2_integration.chat_integration.id}"
}

resource "aws_apigatewayv2_route" "rest_api_route" {
  api_id    = aws_apigatewayv2_api.rest_api.id
  route_key = "ANY /{proxy+}"
  target    = "integrations/${aws_apigatewayv2_integration.rest_api_integration.id}"
}

resource "aws_lambda_permission" "apigw_invoke_rest_api" {
  statement_id  = "AllowExecutionFromAPIGatewayREST"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.api.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.rest_api.execution_arn}/*/*"
}

resource "aws_lambda_permission" "apigw_invoke_chat" {
  statement_id  = "AllowExecutionFromAPIGatewayChat"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.chat.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.rest_api.execution_arn}/*/*"
}
