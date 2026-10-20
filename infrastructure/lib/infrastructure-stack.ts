import * as cdk from 'aws-cdk-lib';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import { Construct } from 'constructs';

import { quanticConfig } from './config';
import { AgentRuntimeRole } from './constructs/agent-runtime-role';
import { DatabaseConstruct } from './constructs/database';
import { DatabaseAccessConstruct } from './constructs/database-access';
import { HelloWorldRuntime } from './constructs/hello-world-runtime';
import { NetworkConstruct } from './constructs/network';

export class QuanticHrAgentStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    cdk.Tags.of(this).add('project', quanticConfig.project);
    cdk.Tags.of(this).add('env', quanticConfig.environment);

    const network = new NetworkConstruct(this, 'Network');
    const database = new DatabaseConstruct(this, 'Database', {
      vpc: network.vpc,
    });
    const databaseAccess = new DatabaseAccessConstruct(this, 'DatabaseAccess', {
      vpc: network.vpc,
      securityGroup: network.adminSecurityGroup,
    });
    const runtimeRole = new AgentRuntimeRole(this, 'AgentRuntime', {
      cluster: database.cluster,
    });
    const helloWorld = new HelloWorldRuntime(this, 'HelloWorld', {
      vpc: network.vpc,
      securityGroup: network.runtimeSecurityGroup,
      executionRole: runtimeRole.role,
    });

    database.cluster.connections.allowDefaultPortFrom(
      network.runtimeSecurityGroup,
      'PostgreSQL from the Quantic AgentCore runtime',
    );
    database.cluster.connections.allowDefaultPortFrom(
      databaseAccess.instance,
      'PostgreSQL from the Quantic SSM admin host',
    );

    const runtimeSubnets = network.vpc.selectSubnets({
      subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS,
    });

    new cdk.CfnOutput(this, 'RuntimeSubnetIds', {
      value: runtimeSubnets.subnetIds.join(','),
      description: 'Private subnets used by the AgentCore Hello World runtime.',
    });
    new cdk.CfnOutput(this, 'RuntimeSecurityGroupId', {
      value: network.runtimeSecurityGroup.securityGroupId,
    });
    new cdk.CfnOutput(this, 'RuntimeRoleArn', {
      value: runtimeRole.role.roleArn,
    });
    new cdk.CfnOutput(this, 'HelloWorldRuntimeArn', {
      value: helloWorld.runtime.agentRuntimeArn,
    });
  }
}
