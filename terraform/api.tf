resource "aws_apigatewayv2_api" "this" {
  name          = var.name
  protocol_type = "HTTP"
  description   = "Checkout fraud scoring API"
}

resource "aws_apigatewayv2_integration" "fn" {
  api_id                 = aws_apigatewayv2_api.this.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.fn.invoke_arn
  payload_format_version = "2.0"
  timeout_milliseconds   = 15000
}

resource "aws_apigatewayv2_route" "score" {
  #checkov:skip=CKV_AWS_309:Authorization is a variable; it defaults to AWS_IAM.
  api_id             = aws_apigatewayv2_api.this.id
  route_key          = "POST /checkouts"
  target             = "integrations/${aws_apigatewayv2_integration.fn.id}"
  authorization_type = var.api_authorization
}

resource "aws_apigatewayv2_route" "get" {
  #checkov:skip=CKV_AWS_309:Authorization is a variable; it defaults to AWS_IAM.
  api_id             = aws_apigatewayv2_api.this.id
  route_key          = "GET /checkouts/{order_id}"
  target             = "integrations/${aws_apigatewayv2_integration.fn.id}"
  authorization_type = var.api_authorization
}

resource "aws_cloudwatch_log_group" "api" {
  #checkov:skip=CKV_AWS_158:Access logs hold no card data; default encryption is used.
  #checkov:skip=CKV_AWS_338:Retention is configurable; 30 days is enough for a demo.
  name              = "/aws/apigateway/${var.name}"
  retention_in_days = var.log_retention_days
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.this.id
  name        = "$default"
  auto_deploy = true

  default_route_settings {
    throttling_rate_limit  = var.throttle_rate_limit
    throttling_burst_limit = var.throttle_burst_limit
  }

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.api.arn
    format = jsonencode({
      requestId = "$context.requestId"
      ip        = "$context.identity.sourceIp"
      route     = "$context.routeKey"
      status    = "$context.status"
      latencyMs = "$context.responseLatency"
      caller    = "$context.identity.userArn"
    })
  }
}

resource "aws_lambda_permission" "api" {
  statement_id  = "AllowApiGateway"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.fn.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.this.execution_arn}/*/*"
}
