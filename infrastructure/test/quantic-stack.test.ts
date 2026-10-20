import * as cdk from 'aws-cdk-lib';
import { Match, Template } from 'aws-cdk-lib/assertions';

import { cafeFausseAurora, quanticConfig, resolveDatabaseMode } from '../lib/config';
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

  test('does not name Café Fausse or AEA resources', () => {
    for (const forbidden of [
      'cafe-fausse',
      'cafe_fausse',
      'CafeFausse',
      'AeaSandbox',
      'aea/sandbox',
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

  test('uses one NAT and keeps Aurora on isolated subnets', () => {
    template.resourceCountIs('AWS::EC2::NatGateway', 1);
    template.resourceCountIs('AWS::EC2::VPCPeeringConnection', 0);

    const groups = template.findResources('AWS::RDS::DBSubnetGroup');
    const group = Object.values(groups)[0] as {
      Properties: { SubnetIds: Array<{ Ref: string }> };
    };
    expect(group.Properties.SubnetIds.length).toBeGreaterThan(0);
    for (const subnet of group.Properties.SubnetIds) {
      expect(subnet.Ref.toLowerCase()).toContain('isolated');
    }
  });
});

describe('Aurora encryption and database ingress', () => {
  const template = synthesize();

  test('encrypts the new quantic_hr cluster and enables IAM auth', () => {
    template.hasResourceProperties('AWS::RDS::DBCluster', {
      StorageEncrypted: true,
      EnableIAMDatabaseAuthentication: true,
      DatabaseName: 'quantic_hr',
      Engine: 'aurora-postgresql',
      EngineVersion: '17.4',
      DeletionProtection: true,
      ServerlessV2ScalingConfiguration: {
        MinCapacity: 0.5,
        MaxCapacity: 2,
      },
    });
    template.hasResourceProperties('AWS::SecretsManager::Secret', {
      Name: 'quantic-hr-agent/dev/database/admin',
    });
  });

  test('allows PostgreSQL only from the runtime and admin security groups', () => {
    const ingress = Object.values(template.findResources('AWS::EC2::SecurityGroupIngress'));
    expect(ingress).toHaveLength(2);
    for (const rule of ingress) {
      const properties = rule.Properties as {
        IpProtocol: string;
        FromPort: number;
        ToPort: number;
        CidrIp?: string;
        SourceSecurityGroupId?: unknown;
      };
      expect(properties.IpProtocol).toBe('tcp');
      expect(properties.ToPort).toEqual(properties.FromPort);
      expect(JSON.stringify(properties.FromPort)).toContain('Endpoint.Port');
      expect(properties.CidrIp).toBeUndefined();
      expect(properties.SourceSecurityGroupId).toBeDefined();
    }
  });
});

describe('runtime IAM scope', () => {
  const template = synthesize();

  test('limits the runtime role to selected models, IAM database auth, and its log group', () => {
    const runtimeRoleId = Object.entries(template.findResources('AWS::IAM::Role')).find(
      ([, role]) =>
        (role as { Properties?: { RoleName?: string } }).Properties?.RoleName ===
        'quantic-hr-agent-dev-runtime',
    )?.[0];
    expect(runtimeRoleId).toBeDefined();

    const policies = Object.values(template.findResources('AWS::IAM::Policy')).filter((policy) =>
      JSON.stringify(policy).includes(`"${runtimeRoleId}"`),
    );
    expect(policies.length).toBeGreaterThan(0);

    const document = JSON.stringify(policies);
    expect(document).toContain('bedrock:InvokeModel');
    expect(document).toContain('rds-db:connect');
    expect(document).toContain(quanticConfig.embeddingModelId);
    expect(document).toContain(quanticConfig.chatInferenceProfileId);
    expect(document).toContain('logs:PutLogEvents');
    expect(document).not.toContain('secretsmanager:');
    expect(document).not.toContain('cafe-fausse');
    expect(document).not.toContain('"Action":"*"');
    expect(document).not.toContain('bedrock:*');
    expect(document).toContain('Sid":"XRayAccess');
    expect(document).toContain('Sid":"CloudWatchMetrics');
  });
});

describe('AgentCore Hello World runtime', () => {
  const template = synthesize();
  const json = JSON.stringify(template.toJSON());

  test('creates one VPC Hello World runtime and no MCP or RAG services', () => {
    template.resourceCountIs('AWS::BedrockAgentCore::Runtime', 1);
    template.hasResourceProperties('AWS::BedrockAgentCore::Runtime', {
      AgentRuntimeName: quanticConfig.helloWorldRuntimeName,
      NetworkConfiguration: {
        NetworkMode: 'VPC',
      },
      ProtocolConfiguration: 'HTTP',
    });
    expect(json).not.toContain('search_policy_documents');
    expect(json).not.toContain('AWS::BedrockAgentCore::Gateway');
  });
});

describe('reuse-cafe-fausse database mode', () => {
  const template = synthesize({ quanticDatabaseMode: 'reuse-cafe-fausse' });
  const json = JSON.stringify(template.toJSON());

  test('does not create Aurora, secrets, or security-group ingress', () => {
    template.resourceCountIs('AWS::RDS::DBCluster', 0);
    template.resourceCountIs('AWS::RDS::DBInstance', 0);
    template.resourceCountIs('AWS::SecretsManager::Secret', 0);
    template.resourceCountIs('AWS::EC2::SecurityGroupIngress', 0);
    template.resourceCountIs('AWS::EC2::Instance', 0);
    template.resourceCountIs('AWS::BedrockAgentCore::Runtime', 1);
    template.resourceCountIs('AWS::EC2::NatGateway', 1);
  });

  test('references the Café cluster resource id for IAM only and does not target AEA', () => {
    expect(json).toContain(cafeFausseAurora.clusterResourceIdentifier);
    expect(json).toContain(cafeFausseAurora.clusterIdentifier);
    expect(json).not.toContain('AeaSandbox');
    expect(json).not.toContain('aea/sandbox');
  });

  test('rejects an unknown database mode', () => {
    expect(() =>
      resolveDatabaseMode({ node: { tryGetContext: () => 'drop-and-replace' } }),
    ).toThrow(/Unknown quanticDatabaseMode/);
  });
});
