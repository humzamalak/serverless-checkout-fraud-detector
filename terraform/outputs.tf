output "api_url" {
  value = aws_apigatewayv2_api.this.api_endpoint
}

output "table_name" {
  value = aws_dynamodb_table.this.name
}

output "lambda_function_name" {
  value = aws_lambda_function.fn.function_name
}
