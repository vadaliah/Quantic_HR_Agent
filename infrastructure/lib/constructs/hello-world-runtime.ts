import * as path from 'path';
import * as cdk from 'aws-cdk-lib';
import * as agentcore from 'aws-cdk-lib/aws-bedrockagentcore';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as iam from 'aws-cdk-lib/aws-iam';
import { Construct } from 'constructs';

import { quanticConfig } from '../config';

export interface HelloWorldRuntimeProps {
  vpc: ec2.IVpc;
  securityGroup: ec2.ISecurityGroup;
  executionRole: iam.IRole;
}

export class HelloWorldRuntime extends Construct {
  public readonly runtime: agentcore.Runtime;

  constructor(scope: Construct, id: string, props: HelloWorldRuntimeProps) {
    super(scope, id);

    const artifact = agentcore.AgentRuntimeArtifact.fromCodeAsset({
      path: path.join(__dirname, '..', '..', '..', 'runtime', 'hello_world'),
      runtime: agentcore.AgentCoreRuntime.PYTHON_3_12,
      entrypoint: ['python', 'main.py'],
      exclude: ['**/__pycache__/**', '**/*.pyc', 'test_*.py'],
    });

    this.runtime = new agentcore.Runtime(this, 'Runtime', {
      runtimeName: quanticConfig.helloWorldRuntimeName,
      description: 'Minimal AgentCore Hello World. No RAG, MCP tools, or HR workflows.',
      executionRole: props.executionRole,
      protocolConfiguration: agentcore.ProtocolType.HTTP,
      agentRuntimeArtifact: artifact,
      networkConfiguration: agentcore.RuntimeNetworkConfiguration.usingVpc(this, {
        vpc: props.vpc,
        vpcSubnets: { subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS },
        securityGroups: [props.securityGroup],
      }),
      environmentVariables: {
        QUANTIC_PROJECT: quanticConfig.project,
        QUANTIC_ENV: quanticConfig.environment,
      },
      manageDeliveryResourcePolicy: false,
      tags: {
        project: quanticConfig.project,
        env: quanticConfig.environment,
        purpose: 'hello-world',
      },
    });
  }
}
