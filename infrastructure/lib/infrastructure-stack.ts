import * as cdk from 'aws-cdk-lib';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as rds from 'aws-cdk-lib/aws-rds';
import { Construct } from 'constructs';

import {
  cafeFausseAurora,
  quanticConfig,
  resolveChatModel,
  resolveDatabaseMode,
  resolveDeletionProtection,
  resolveRuntimeImage,
} from './config';
import { AgentContainerRuntime } from './constructs/agent-container-runtime';
import { AgentRuntimeRole } from './constructs/agent-runtime-role';
import { DatabaseConstruct } from './constructs/database';
import { DatabaseAccessConstruct } from './constructs/database-access';
import { ExistingCafeFausseDatabase } from './constructs/existing-database';
import { HelloWorldRuntime } from './constructs/hello-world-runtime';
import { NetworkConstruct } from './constructs/network';

export class QuanticHrAgentStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    cdk.Tags.of(this).add('project', quanticConfig.project);
    cdk.Tags.of(this).add('env', quanticConfig.environment);

    const databaseMode = resolveDatabaseMode(this);
    const chatModel = resolveChatModel(this);
    const deletionProtection = resolveDeletionProtection(this);
    const runtimeImage = resolveRuntimeImage(this);
    const network = new NetworkConstruct(this, 'Network');

    let cluster: rds.IDatabaseCluster;
    let databaseEndpoint: { hostname: string; port: string } | undefined;
    if (databaseMode === 'reuse-cafe-fausse') {
      cluster = new ExistingCafeFausseDatabase(this, 'ExistingDatabase').cluster;
    } else {
      const database = new DatabaseConstruct(this, 'Database', {
        vpc: network.vpc,
        deletionProtection,
      });
      const databaseAccess = new DatabaseAccessConstruct(this, 'DatabaseAccess', {
        vpc: network.vpc,
        securityGroup: network.adminSecurityGroup,
      });
      cluster = database.cluster;
      databaseEndpoint = {
        hostname: database.cluster.clusterEndpoint.hostname,
        port: cdk.Token.asString(database.cluster.clusterEndpoint.port),
      };
      database.cluster.connections.allowDefaultPortFrom(
        network.runtimeSecurityGroup,
        'PostgreSQL from the Quantic AgentCore runtime',
      );
      database.cluster.connections.allowDefaultPortFrom(
        databaseAccess.instance,
        'PostgreSQL from the Quantic SSM admin host',
      );
    }

    const runtimeRole = new AgentRuntimeRole(this, 'AgentRuntime', {
      cluster,
      chatModel,
    });
    const runtime =
      runtimeImage === 'agent'
        ? new AgentContainerRuntime(this, 'Agent', {
            vpc: network.vpc,
            securityGroup: network.runtimeSecurityGroup,
            executionRole: runtimeRole.role,
            chatModel,
            database: databaseEndpoint,
          }).runtime
        : new HelloWorldRuntime(this, 'HelloWorld', {
            vpc: network.vpc,
            securityGroup: network.runtimeSecurityGroup,
            executionRole: runtimeRole.role,
          }).runtime;

    const runtimeSubnets = network.vpc.selectSubnets({
      subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS,
    });

    new cdk.CfnOutput(this, 'DatabaseMode', {
      value: databaseMode,
    });
    new cdk.CfnOutput(this, 'ChatInferenceProfileId', {
      value: chatModel.inferenceProfileId,
      description: 'Set BEDROCK_CHAT_INFERENCE_PROFILE to this value for the app.',
    });
    new cdk.CfnOutput(this, 'DatabaseClusterIdentifier', {
      value:
        databaseMode === 'reuse-cafe-fausse'
          ? cafeFausseAurora.clusterIdentifier
          : cluster.clusterIdentifier,
    });
    new cdk.CfnOutput(this, 'RuntimeSubnetIds', {
      value: runtimeSubnets.subnetIds.join(','),
      description: 'Private subnets used by the AgentCore runtime.',
    });
    new cdk.CfnOutput(this, 'RuntimeSecurityGroupId', {
      value: network.runtimeSecurityGroup.securityGroupId,
    });
    new cdk.CfnOutput(this, 'RuntimeRoleArn', {
      value: runtimeRole.role.roleArn,
    });
    new cdk.CfnOutput(this, 'RuntimeImage', {
      value: runtimeImage,
    });
    new cdk.CfnOutput(this, 'AgentRuntimeArn', {
      value: runtime.agentRuntimeArn,
    });
  }
}
