// NOT USED: hosting is Render (docs/DEPLOY_RENDER.md). Kept as a record of the AgentCore path.
import * as path from 'path';
import * as agentcore from 'aws-cdk-lib/aws-bedrockagentcore';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import { Platform } from 'aws-cdk-lib/aws-ecr-assets';
import * as iam from 'aws-cdk-lib/aws-iam';
import { IgnoreMode } from 'aws-cdk-lib';
import { Construct } from 'constructs';

import { ChatModel, quanticConfig } from '../config';

export interface AgentContainerRuntimeProps {
  vpc: ec2.IVpc;
  securityGroup: ec2.ISecurityGroup;
  executionRole: iam.IRole;
  chatModel: ChatModel;
  /** Writer endpoint of the Quantic cluster. Omitted in reuse-cafe-fausse mode. */
  database?: { hostname: string; port: string };
}

/**
 * The real Quantic HR agent (FastAPI + LangGraph + stdio FastMCP) as an AgentCore
 * Runtime container. The repository-root Dockerfile is built for linux/arm64 and
 * pushed to the CDK bootstrap ECR repository by a DockerImageAsset at deploy time;
 * synth stays offline. The runtime role gets ECR pull on that repository only.
 */
export class AgentContainerRuntime extends Construct {
  public readonly runtime: agentcore.Runtime;

  constructor(scope: Construct, id: string, props: AgentContainerRuntimeProps) {
    super(scope, id);

    const artifact = agentcore.AgentRuntimeArtifact.fromAsset(
      path.join(__dirname, '..', '..', '..'),
      {
        platform: Platform.LINUX_ARM64,
        file: 'Dockerfile',
        ignoreMode: IgnoreMode.DOCKER,
      },
    );

    const environmentVariables: Record<string, string> = {
      QUANTIC_PROJECT: quanticConfig.project,
      QUANTIC_ENV: quanticConfig.environment,
      AWS_REGION: quanticConfig.region,
      BEDROCK_CHAT_INFERENCE_PROFILE: props.chatModel.inferenceProfileId,
      BEDROCK_EMBEDDING_MODEL: quanticConfig.embeddingModelId,
      QUANTIC_AGENT_MODE: 'auto',
      QUANTIC_RETRIEVAL: 'auto',
      DB_NAME: quanticConfig.databaseName,
      DB_USER: quanticConfig.runtimeDbUsername,
      DB_IAM_AUTH: 'true',
      DB_SSLMODE: 'require',
    };
    if (props.database) {
      environmentVariables.DB_HOST = props.database.hostname;
      environmentVariables.DB_PORT = props.database.port;
    }

    this.runtime = new agentcore.Runtime(this, 'Runtime', {
      runtimeName: quanticConfig.agentRuntimeName,
      description: 'Quantic HR agent: FastAPI + LangGraph + stdio MCP, Bedrock and Aurora pgvector.',
      executionRole: props.executionRole,
      protocolConfiguration: agentcore.ProtocolType.HTTP,
      agentRuntimeArtifact: artifact,
      networkConfiguration: agentcore.RuntimeNetworkConfiguration.usingVpc(this, {
        vpc: props.vpc,
        vpcSubnets: { subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS },
        securityGroups: [props.securityGroup],
      }),
      environmentVariables,
      manageDeliveryResourcePolicy: false,
      tags: {
        project: quanticConfig.project,
        env: quanticConfig.environment,
        purpose: 'hr-agent',
      },
    });
  }
}
