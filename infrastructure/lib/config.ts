import { Construct } from "constructs";

export interface McpLambdaConfig {
  projectPrefix: string;
  awsRegion: string;
  awsAccountId: string;
  ecrRepositoryName: string;
  imageTag: string;
  lambdaMemoryMb: number;
  lambdaTimeoutSeconds: number;
  // OpenSearch configuration for cross-account access
  opensearchHost: string;
  opensearchRegion: string;
  opensearchAccountId: string;
  opensearchDomainName: string;
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

  // OpenSearch configuration - defaults match the dev environment
  const opensearchHost =
    process.env.CDK_OPENSEARCH_HOST ||
    scope.node.tryGetContext("opensearchHost") ||
    "search-opensearch-dev-01-t4a3j3mz3m5zedfbx2tnhkd2oi.us-west-2.es.amazonaws.com";

  const opensearchRegion =
    process.env.CDK_OPENSEARCH_REGION ||
    scope.node.tryGetContext("opensearchRegion") ||
    "us-west-2";

  const opensearchAccountId =
    process.env.CDK_OPENSEARCH_ACCOUNT_ID ||
    scope.node.tryGetContext("opensearchAccountId") ||
    ""; // Required for cross-account access

  const opensearchDomainName =
    process.env.CDK_OPENSEARCH_DOMAIN_NAME ||
    scope.node.tryGetContext("opensearchDomainName") ||
    "opensearch-dev-01";

  return {
    projectPrefix,
    awsRegion,
    awsAccountId,
    ecrRepositoryName,
    imageTag,
    lambdaMemoryMb,
    lambdaTimeoutSeconds,
    opensearchHost,
    opensearchRegion,
    opensearchAccountId,
    opensearchDomainName,
  };
}
