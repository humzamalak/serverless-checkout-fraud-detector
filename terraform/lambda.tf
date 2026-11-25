data "archive_file" "fn" {
  type        = "zip"
  source_dir  = "${path.module}/../src"
  output_path = "${path.module}/build/fraud.zip"
  excludes    = ["**/__pycache__/**"]
}

resource "aws_cloudwatch_log_group" "fn" {
  #checkov:skip=CKV_AWS_158:Logs hold no card data; default encryption is used.
  #checkov:skip=CKV_AWS_338:Retention is configurable; 30 days is enough for a demo.
  name              = "/aws/lambda/${var.name}"
  retention_in_days = var.log_retention_days
}

resource "aws_lambda_function" "fn" {
  #checkov:skip=CKV_AWS_117:The function calls only public AWS endpoints; a VPC adds NAT cost and no benefit here.
  #checkov:skip=CKV_AWS_116:Synchronous API invocations cannot use a DLQ.
  #checkov:skip=CKV_AWS_272:Code signing is out of scope for this demo.
  #checkov:skip=CKV_AWS_173:Environment variables hold no secrets.
  function_name                  = var.name
  description                    = "Scores checkouts with rules and Amazon Bedrock"
  role                           = aws_iam_role.fn.arn
  runtime                        = "python3.12"
  architectures                  = ["arm64"]
  handler                        = "fraud.handler.lambda_handler"
  filename                       = data.archive_file.fn.output_path
  source_code_hash               = data.archive_file.fn.output_base64sha256
  timeout                        = 15
  memory_size                    = 256
  reserved_concurrent_executions = 50

  environment {
    variables = {
      TABLE_NAME       = aws_dynamodb_table.this.name
      BEDROCK_MODEL_ID = var.bedrock_model_id
      BEDROCK_ENABLED  = tostring(var.bedrock_enabled)
      APPROVE_BELOW    = tostring(var.approve_below)
      DECLINE_AT       = tostring(var.decline_at)
    }
  }

  tracing_config {
    mode = "Active"
  }

  depends_on = [aws_cloudwatch_log_group.fn]
}

data "aws_iam_policy_document" "assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "fn" {
  name               = "${var.name}-lambda"
  assume_role_policy = data.aws_iam_policy_document.assume.json
}

data "aws_iam_policy_document" "fn" {
  statement {
    sid       = "Logs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.fn.arn}:*"]
  }

  statement {
    sid = "Table"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:UpdateItem",
      "dynamodb:Query",
      "dynamodb:BatchWriteItem",
    ]
    resources = [aws_dynamodb_table.this.arn]
  }

  # A cross-region inference profile routes to the model in several regions,
  # so the foundation-model ARN uses a region wildcard.
  statement {
    sid     = "Bedrock"
    actions = ["bedrock:InvokeModel"]
    resources = [
      "arn:${data.aws_partition.current.partition}:bedrock:*::foundation-model/*",
      "arn:${data.aws_partition.current.partition}:bedrock:${var.region}:${data.aws_caller_identity.current.account_id}:inference-profile/*",
    ]
  }

  statement {
    sid       = "Tracing"
    actions   = ["xray:PutTraceSegments", "xray:PutTelemetryRecords"]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "fn" {
  name   = "fraud-scorer"
  role   = aws_iam_role.fn.id
  policy = data.aws_iam_policy_document.fn.json
}
