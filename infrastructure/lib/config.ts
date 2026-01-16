import { Construct } from "constructs";

export interface McpLambdaConfig {
  projectPrefix: string;
  awsRegion: string;
  awsAccountId: string;
  ecrRepositoryName: string;
  imageTag: string;
  lambdaMemoryMb: number;
  lambdaTimeoutSeconds: number;
  classSearchApiBaseUrl: string;
}

export function loadConfig(scope: Construct): McpLambdaConfig {
  const projectPrefix =
    process.env.CDK_PROJECT_PREFIX ||
    scope.node.tryGetContext("projectPrefix") ||
    "mcp-docker-lambda";

  const awsRegion =
    process.env.CDK_AWS_REGION ||
    scope.node.tryGetContext("awsRegion") ||
    process.env.AWS_DEFAULT_REGION ||
    "us-west-2";

  const awsAccountId =
    process.env.CDK_AWS_ACCOUNT_ID ||
    scope.node.tryGetContext("awsAccountId") ||
    process.env.AWS_ACCOUNT_ID ||
    "";

  const ecrRepositoryName =
    process.env.CDK_ECR_REPOSITORY_NAME ||
    scope.node.tryGetContext("ecrRepositoryName") ||
    `${projectPrefix}-mcp-tool`;

  const imageTag =
    process.env.CDK_IMAGE_TAG ||
    scope.node.tryGetContext("imageTag") ||
    "latest";

  const lambdaMemoryMb = parseInt(
    process.env.CDK_LAMBDA_MEMORY_MB ||
      scope.node.tryGetContext("lambdaMemoryMb") ||
      "512",
    10
  );

  const lambdaTimeoutSeconds = parseInt(
    process.env.CDK_LAMBDA_TIMEOUT_SECONDS ||
      scope.node.tryGetContext("lambdaTimeoutSeconds") ||
      "30",
    10
  );

  const classSearchApiBaseUrl =
    process.env.CDK_CLASS_SEARCH_API_BASE_URL ||
    scope.node.tryGetContext("classSearchApiBaseUrl") ||
    "https://classes.boisestate.edu";

  return {
    projectPrefix,
    awsRegion,
    awsAccountId,
    ecrRepositoryName,
    imageTag,
    lambdaMemoryMb,
    lambdaTimeoutSeconds,
    classSearchApiBaseUrl,
  };
}
