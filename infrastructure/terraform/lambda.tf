resource "aws_s3_bucket" "lambda_deploy" {
  bucket        = "${local.prefix}-lambda-deploy-${data.aws_caller_identity.current.account_id}"
  force_destroy = true
}

resource "aws_s3_object" "lambda_zip" {
  bucket = aws_s3_bucket.lambda_deploy.id
  key    = "sentinelai-lambda.zip"
  source = "${path.module}/../build/sentinelai-lambda.zip"
}

resource "aws_s3_object" "chat_lambda_zip" {
  bucket = aws_s3_bucket.lambda_deploy.id
  key    = "sentinelai-chat-lambda.zip"
  source = "${path.module}/../build/sentinelai-chat-lambda.zip"
}

resource "aws_lambda_function" "api" {
  function_name    = "${local.prefix}-api"
  role             = aws_iam_role.lambda_exec.arn
  handler          = "lambda.handler.handler"
  runtime          = "python3.11"
  memory_size      = 512
  timeout          = 29

  s3_bucket        = aws_s3_bucket.lambda_deploy.id
  s3_key           = aws_s3_object.lambda_zip.key
  source_code_hash = filebase64sha256("${path.module}/../build/sentinelai-lambda.zip")

  environment {
    variables = {
      ENVIRONMENT           = var.environment
      STORAGE_BACKEND       = var.storage_backend
      DYNAMODB_TABLE_PREFIX = local.dynamodb_table_prefix
      EVENTBRIDGE_BUS_NAME  = local.eventbridge_bus_name
      LOG_LEVEL             = "INFO"
      WAF_WEBSOCKET_API_ENDPOINT = "https://${aws_apigatewayv2_api.waf_websocket.id}.execute-api.${var.aws_region}.amazonaws.com/${var.waf_websocket_stage}"
      CORS_ORIGINS          = "http://localhost:5173,http://localhost:5174,http://localhost:3000,https://${aws_cloudfront_distribution.frontend_cdn.domain_name}"
      LITELLM_MODEL         = var.litellm_model
      CEREBRAS_API_KEY      = var.cerebras_api_key
      CEREBRAS_MODEL        = "cerebras/gpt-oss-120b"
      COPILOT_SKIP_TEMPLATES = "false"
    }
  }
}

resource "aws_lambda_function" "chat" {
  function_name    = "${local.prefix}-chat"
  role             = aws_iam_role.lambda_exec.arn
  handler          = "chat_handler.handler"
  runtime          = "python3.11"
  memory_size      = 1024
  timeout          = 29

  s3_bucket        = aws_s3_bucket.lambda_deploy.id
  s3_key           = aws_s3_object.chat_lambda_zip.key
  source_code_hash = filebase64sha256("${path.module}/../build/sentinelai-chat-lambda.zip")

  environment {
    variables = {
      ENVIRONMENT           = var.environment
      LOG_LEVEL             = "INFO"
      CORS_ORIGINS          = "http://localhost:5173,http://localhost:5174,http://localhost:3000,https://${aws_cloudfront_distribution.frontend_cdn.domain_name}"
      LITELLM_MODEL         = "cerebras/gemma-4-31b"
      CEREBRAS_API_KEY      = var.cerebras_api_key
      CEREBRAS_MODEL        = "cerebras/gemma-4-31b"
      GOVERNANCE_API_URL    = "${aws_apigatewayv2_api.rest_api.api_endpoint}/v1"
    }
  }
}



resource "aws_lambda_function" "waf_ws" {
  function_name    = "${local.prefix}-waf-ws"
  role             = aws_iam_role.lambda_exec.arn
  handler          = "lambda.ws_handler.handler"
  runtime          = "python3.11"
  memory_size      = 256
  timeout          = 29

  s3_bucket        = aws_s3_bucket.lambda_deploy.id
  s3_key           = aws_s3_object.lambda_zip.key
  source_code_hash = filebase64sha256("${path.module}/../build/sentinelai-lambda.zip")

  environment {
    variables = {
      ENVIRONMENT           = var.environment
      STORAGE_BACKEND       = var.storage_backend
      DYNAMODB_TABLE_PREFIX = local.dynamodb_table_prefix
      LOG_LEVEL             = "INFO"
    }
  }
}
