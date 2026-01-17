import * as cdk from "aws-cdk-lib";
import * as ecr from "aws-cdk-lib/aws-ecr";
import * as lambda from "aws-cdk-lib/aws-lambda";
import * as iam from "aws-cdk-lib/aws-iam";
import * as logs from "aws-cdk-lib/aws-logs";
import { Construct } from "constructs";
import { McpLambdaConfig } from "./config";

export interface McpLambdaStackProps extends cdk.StackProps {
  config: McpLambdaConfig;
}

export class McpLambdaStack extends cdk.Stack {
  public readonly ecrRepository: ecr.IRepository;
  public readonly lambdaFunction: lambda.Function;
  public readonly functionUrl: lambda.FunctionUrl;

  constructor(scope: Construct, id: string, props: McpLambdaStackProps) {
    super(scope, id, props);

    const { config } = props;

    // Import existing ECR repository (created by push-docker.sh)
    this.ecrRepository = ecr.Repository.fromRepositoryName(
      this,
      "McpToolRepository",
      config.ecrRepositoryName
    );

    // Create Lambda execution role
    const lambdaRole = new iam.Role(this, "McpLambdaRole", {
      roleName: `${config.projectPrefix}-lambda-role`,
      assumedBy: new iam.ServicePrincipal("lambda.amazonaws.com"),
      managedPolicies: [
        iam.ManagedPolicy.fromAwsManagedPolicyName(
          "service-role/AWSLambdaBasicExecutionRole"
        ),
      ],
    });

    // Add OpenSearch access policy for cross-account access
    // This allows the Lambda to sign requests to OpenSearch in another account
    if (config.opensearchAccountId && config.opensearchDomainName) {
      lambdaRole.addToPolicy(
        new iam.PolicyStatement({
          effect: iam.Effect.ALLOW,
          actions: [
            "es:ESHttpGet",
            "es:ESHttpPost",
            "es:ESHttpHead",
          ],
          resources: [
            `arn:aws:es:${config.opensearchRegion}:${config.opensearchAccountId}:domain/${config.opensearchDomainName}/*`,
          ],
        })
      );
    }

    // Create CloudWatch log group
    const logGroup = new logs.LogGroup(this, "McpLambdaLogGroup", {
      logGroupName: `/aws/lambda/${config.projectPrefix}-mcp-tool`,
      retention: logs.RetentionDays.TWO_WEEKS,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    // Create Lambda function from ECR image
    this.lambdaFunction = new lambda.DockerImageFunction(
      this,
      "McpToolFunction",
      {
        functionName: `${config.projectPrefix}-mcp-tool`,
        code: lambda.DockerImageCode.fromEcr(this.ecrRepository, {
          tagOrDigest: config.imageTag,
        }),
        memorySize: config.lambdaMemoryMb,
        timeout: cdk.Duration.seconds(config.lambdaTimeoutSeconds),
        role: lambdaRole,
        logGroup: logGroup,
        environment: {
          LOG_LEVEL: "INFO",
          OPENSEARCH_HOST: config.opensearchHost,
          OPENSEARCH_REGION: config.opensearchRegion,
        },
        description: "MCP Tool running in a Docker container",
      }
    );

    // Create Function URL with IAM authentication (SigV4)
    this.functionUrl = this.lambdaFunction.addFunctionUrl({
      authType: lambda.FunctionUrlAuthType.AWS_IAM,
      cors: {
        allowedOrigins: ["*"],
        allowedMethods: [lambda.HttpMethod.ALL],
        allowedHeaders: ["*"],
      },
    });

    // Allow any authenticated principal in the same account to invoke the function URL
    this.lambdaFunction.addPermission("AllowSameAccountInvoke", {
      principal: new iam.AccountPrincipal(cdk.Stack.of(this).account),
      action: "lambda:InvokeFunctionUrl",
      functionUrlAuthType: lambda.FunctionUrlAuthType.AWS_IAM,
    });

    // Outputs
    new cdk.CfnOutput(this, "EcrRepositoryUri", {
      value: this.ecrRepository.repositoryUri,
      description: "ECR Repository URI",
      exportName: `${config.projectPrefix}-ecr-repository-uri`,
    });

    new cdk.CfnOutput(this, "LambdaFunctionArn", {
      value: this.lambdaFunction.functionArn,
      description: "Lambda Function ARN",
      exportName: `${config.projectPrefix}-lambda-function-arn`,
    });

    new cdk.CfnOutput(this, "LambdaFunctionUrl", {
      value: this.functionUrl.url,
      description: "Lambda Function URL (MCP endpoint)",
      exportName: `${config.projectPrefix}-lambda-function-url`,
    });
  }
}
