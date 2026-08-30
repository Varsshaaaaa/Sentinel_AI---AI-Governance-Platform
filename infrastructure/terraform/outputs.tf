output "waf_websocket_url" {
  description = "The WebSocket URL for the frontend WAF Stream"
  value       = "wss://${aws_apigatewayv2_api.waf_websocket.id}.execute-api.${var.aws_region}.amazonaws.com/${var.waf_websocket_stage}"
}

output "waf_websocket_api_endpoint" {
  description = "The API Endpoint for backend connection management"
  value       = "https://${aws_apigatewayv2_api.waf_websocket.id}.execute-api.${var.aws_region}.amazonaws.com/${var.waf_websocket_stage}"
}

output "api_lambda_arn" {
  description = "ARN of the REST API Lambda"
  value       = aws_lambda_function.api.arn
}

output "chat_lambda_arn" {
  description = "ARN of the Agent Chat Lambda (Cerebras testing)"
  value       = aws_lambda_function.chat.arn
}

output "api_url" {
  description = "Public HTTP endpoint for the REST API"
  value       = aws_apigatewayv2_api.rest_api.api_endpoint
}

output "chat_api_url" {
  description = "Agent Chat endpoint served by the dedicated chat Lambda"
  value       = "${aws_apigatewayv2_api.rest_api.api_endpoint}/v1/chat"
}

output "frontend_s3_bucket" {
  description = "S3 Bucket to upload the compiled React UI to"
  value       = aws_s3_bucket.frontend.bucket
}

output "frontend_cloudfront_url" {
  description = "The public CloudFront URL for the SentinelAI Dashboard"
  value       = "https://${aws_cloudfront_distribution.frontend_cdn.domain_name}"
}
