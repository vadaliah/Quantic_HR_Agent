import { Construct } from 'constructs';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as rds from 'aws-cdk-lib/aws-rds';

import { cafeFausseAurora } from '../config';

/**
 * Read-only reference to the Café Fausse Aurora cluster.
 * Security group is imported immutable so this stack cannot add ingress.
 */
export class ExistingCafeFausseDatabase extends Construct {
  public readonly cluster: rds.IDatabaseCluster;

  constructor(scope: Construct, id: string) {
    super(scope, id);

    const securityGroup = ec2.SecurityGroup.fromSecurityGroupId(
      this,
      'ImportedDatabaseSecurityGroup',
      cafeFausseAurora.securityGroupId,
      { mutable: false },
    );

    this.cluster = rds.DatabaseCluster.fromDatabaseClusterAttributes(this, 'ImportedAurora', {
      clusterIdentifier: cafeFausseAurora.clusterIdentifier,
      clusterResourceIdentifier: cafeFausseAurora.clusterResourceIdentifier,
      port: cafeFausseAurora.port,
      securityGroups: [securityGroup],
      engine: rds.DatabaseClusterEngine.auroraPostgres({
        version: rds.AuroraPostgresEngineVersion.VER_17_4,
      }),
    });
  }
}
