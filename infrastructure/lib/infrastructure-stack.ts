import * as cdk from 'aws-cdk-lib';
import { Construct } from 'constructs';

import { assertDatabaseOnlyDeployment, quanticConfig } from './config';
import { DatabaseConstruct } from './constructs/database';
import { NetworkConstruct } from './constructs/network';

export class QuanticHrAgentStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    cdk.Tags.of(this).add('project', quanticConfig.project);
    cdk.Tags.of(this).add('env', quanticConfig.environment);

    assertDatabaseOnlyDeployment(this);

    const network = new NetworkConstruct(this, 'Network');
    const database = new DatabaseConstruct(this, 'Database', {
      vpc: network.vpc,
    });

    new cdk.CfnOutput(this, 'DatabaseName', {
      value: quanticConfig.databaseName,
    });
    new cdk.CfnOutput(this, 'DatabaseClusterIdentifier', {
      value: database.cluster.clusterIdentifier,
    });
    new cdk.CfnOutput(this, 'DatabaseSecretName', {
      value: quanticConfig.secretName,
      description: 'Generated Quantic admin secret. The value is not an output.',
    });
    new cdk.CfnOutput(this, 'DatabaseEndpoint', {
      value: database.cluster.clusterEndpoint.hostname,
    });
  }
}
