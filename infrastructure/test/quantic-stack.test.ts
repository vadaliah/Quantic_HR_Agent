import * as cdk from 'aws-cdk-lib';
import { Match, Template } from 'aws-cdk-lib/assertions';

import { cafeFausseAurora, quanticConfig, resolveDatabaseMode } from '../lib/config';
import { ExistingCafeFausseDatabase } from '../lib/constructs/existing-database';
import { QuanticHrAgentStack } from '../lib/infrastructure-stack';

function synthesize(context: Record<string, string> = {}): Template {
  const app = new cdk.App({ context });
  const stack = new QuanticHrAgentStack(app, quanticConfig.stackName, {
    env: { account: quanticConfig.account, region: quanticConfig.region },
  });
  return Template.fromStack(stack);
}

describe('QuanticHrAgentStack isolation', () => {
  const template = synthesize();
  const json = JSON.stringify(template.toJSON());

  test('does not name or import Café Fausse or AEA resources', () => {
    for (const forbidden of [
      'cafe-fausse',
      'cafe_fausse',
      'CafeFausse',
      'AeaSandbox',
      'aea/sandbox',
      cafeFausseAurora.clusterIdentifier,
      cafeFausseAurora.clusterResourceIdentifier,
      cafeFausseAurora.securityGroupId,
      cafeFausseAurora.secretName,
      cafeFausseAurora.vpcId,
    ]) {
      expect(json).not.toContain(forbidden);
    }
  });

  test('tags the network as the Quantic dev project', () => {
    template.hasResourceProperties('AWS::EC2::VPC', {
      CidrBlock: quanticConfig.vpcCidr,
      Tags: Match.arrayWith([
        { Key: 'env', Value: 'dev' },
        { Key: 'project', Value: 'quantic-hr-agent' },
      ]),
    });
  });

  test('keeps Aurora on isolated subnets and creates no NAT, endpoints, or public network', () => {
    template.resourceCountIs('AWS::EC2::NatGateway', 0);
    template.resourceCountIs('AWS::EC2::EIP', 0);
    template.resourceCountIs('AWS::EC2::InternetGateway', 0);
    template.resourceCountIs('AWS::EC2::VPCEndpoint', 0);
    template.resourceCountIs('AWS::EC2::VPCPeeringConnection', 0);
    template.resourceCountIs('AWS::EC2::Subnet', 2);

    const groups = template.findResources('AWS::RDS::DBSubnetGroup');
    const group = Object.values(groups)[0] as {
      Properties: { SubnetIds: Array<{ Ref: string }> };
    };
    expect(group.Properties.SubnetIds).toHaveLength(2);
    for (const subnet of group.Properties.SubnetIds) {
      expect(subnet.Ref.toLowerCase()).toContain('isolated');
    }
  });
});

describe('empty Aurora database', () => {
  const template = synthesize();
  const json = JSON.stringify(template.toJSON());

  test('creates one encrypted PostgreSQL 17.4 Serverless v2 cluster that can pause', () => {
    template.resourceCountIs('AWS::RDS::DBCluster', 1);
    template.resourceCountIs('AWS::RDS::DBInstance', 1);
    template.hasResourceProperties('AWS::RDS::DBCluster', {
      StorageEncrypted: true,
      EnableIAMDatabaseAuthentication: true,
      DatabaseName: 'quantic_hr_agent',
      Engine: 'aurora-postgresql',
      EngineVersion: '17.4',
      DeletionProtection: true,
      BackupRetentionPeriod: 1,
      MasterUsername: quanticConfig.adminUsername,
      ServerlessV2ScalingConfiguration: {
        MinCapacity: 0,
        MaxCapacity: 2,
        SecondsUntilAutoPause: 300,
      },
    });
    template.hasResourceProperties('AWS::RDS::DBInstance', {
      Engine: 'aurora-postgresql',
      PubliclyAccessible: false,
      AutoMinorVersionUpgrade: false,
      EnablePerformanceInsights: false,
      DBInstanceClass: 'db.serverless',
    });
    template.hasResource('AWS::SecretsManager::Secret', {
      DeletionPolicy: 'Retain',
      UpdateReplacePolicy: 'Retain',
      Properties: {
        Name: 'quantic-hr-agent/dev/database/admin',
      },
    });
    template.resourceCountIs('AWS::SecretsManager::Secret', 1);
  });

  test('does not open PostgreSQL, add schemas, or provision extra runtimes', () => {
    template.resourceCountIs('AWS::EC2::SecurityGroupIngress', 0);
    template.resourceCountIs('AWS::EC2::Instance', 0);
    template.resourceCountIs('AWS::BedrockAgentCore::Runtime', 0);
    template.resourceCountIs('AWS::BedrockAgentCore::Gateway', 0);
    template.resourceCountIs('AWS::KMS::Key', 0);
    template.resourceCountIs('AWS::Logs::LogGroup', 0);
    template.resourceCountIs('AWS::Lambda::Function', 0);
    template.resourceCountIs('AWS::RDS::DBProxy', 0);
    expect(json).not.toContain('CREATE TABLE');
    expect(json).not.toContain('CREATE EXTENSION');
    expect(json).not.toContain('search_policy_documents');
  });

  test('refuses Café reuse and any deployment scope beyond the database', () => {
    expect(() => synthesize({ quanticDatabaseMode: 'reuse-cafe-fausse' })).toThrow(
      /Café Fausse and AEA stay untouched/,
    );
    expect(() => synthesize({ quanticDeploymentScope: 'baseline' })).toThrow(
      /NAT, AgentCore, and admin hosts are excluded/,
    );
    expect(() =>
      resolveDatabaseMode({ node: { tryGetContext: () => 'drop-and-replace' } }),
    ).toThrow(/Café Fausse and AEA stay untouched/);
    expect(() => new ExistingCafeFausseDatabase(new cdk.Stack(), 'Existing')).toThrow(
      /Refusing to import Café Fausse Aurora/,
    );
  });
});
