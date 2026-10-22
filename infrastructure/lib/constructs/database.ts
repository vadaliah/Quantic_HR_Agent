import { RemovalPolicy } from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as rds from 'aws-cdk-lib/aws-rds';
import * as secretsmanager from 'aws-cdk-lib/aws-secretsmanager';

import { quanticConfig } from '../config';

export interface DatabaseConstructProps {
  vpc: ec2.IVpc;
}

export class DatabaseConstruct extends Construct {
  public readonly cluster: rds.DatabaseCluster;
  public readonly secret: secretsmanager.ISecret;
  public readonly securityGroup: ec2.SecurityGroup;

  constructor(scope: Construct, id: string, props: DatabaseConstructProps) {
    super(scope, id);

    this.securityGroup = new ec2.SecurityGroup(this, 'DatabaseSecurityGroup', {
      vpc: props.vpc,
      description: 'Aurora PostgreSQL. Inbound only from approved Quantic groups.',
      allowAllOutbound: false,
    });

    this.cluster = new rds.DatabaseCluster(this, 'AuroraPostgres', {
      engine: rds.DatabaseClusterEngine.auroraPostgres({
        version: rds.AuroraPostgresEngineVersion.VER_17_4,
      }),
      credentials: rds.Credentials.fromGeneratedSecret(quanticConfig.adminUsername, {
        secretName: quanticConfig.secretName,
      }),
      iamAuthentication: true,
      writer: rds.ClusterInstance.serverlessV2('writer'),
      serverlessV2MinCapacity: 0.5,
      serverlessV2MaxCapacity: 2,
      vpc: props.vpc,
      vpcSubnets: {
        subnetType: ec2.SubnetType.PRIVATE_ISOLATED,
      },
      defaultDatabaseName: quanticConfig.databaseName,
      storageEncrypted: true,
      deletionProtection: true,
      removalPolicy: RemovalPolicy.RETAIN,
      securityGroups: [this.securityGroup],
    });

    if (!this.cluster.secret) {
      throw new Error('Database secret was not created');
    }

    this.secret = this.cluster.secret;
  }
}
