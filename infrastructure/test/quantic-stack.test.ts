import * as cdk from 'aws-cdk-lib';
import { Match, Template } from 'aws-cdk-lib/assertions';

import {
  cafeFausseAurora,
  chatModels,
  quanticConfig,
  resolveChatModel,
  resolveDatabaseMode,
  resolveDeletionProtection,
  resolveRuntimeImage,
} from '../lib/config';
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

  test('encrypts the new quantic_hr_agent cluster and enables IAM auth', () => {
    template.hasResourceProperties('AWS::RDS::DBCluster', {
      StorageEncrypted: true,
      EnableIAMDatabaseAuthentication: true,
      DatabaseName: 'quantic_hr_agent',
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

  test('protects and retains the live cluster and its secret by default', () => {
    const clusters = Object.values(template.findResources('AWS::RDS::DBCluster')) as Array<{
      DeletionPolicy?: string;
    }>;
    expect(clusters).toHaveLength(1);
    expect(clusters[0].DeletionPolicy).toBe('Retain');
    const secrets = Object.values(template.findResources('AWS::SecretsManager::Secret')) as Array<{
      DeletionPolicy?: string;
    }>;
    expect(secrets[0].DeletionPolicy).toBe('Retain');
  });

  test('lets cdk destroy remove a throwaway cluster only when asked', () => {
    const throwaway = synthesize({ quanticDeletionProtection: 'false' });
    throwaway.hasResourceProperties('AWS::RDS::DBCluster', { DeletionProtection: false });
    const clusters = Object.values(throwaway.findResources('AWS::RDS::DBCluster')) as Array<{
      DeletionPolicy?: string;
    }>;
    expect(clusters[0].DeletionPolicy).toBe('Delete');
  });

  test('rejects an unknown deletion protection value', () => {
    expect(() =>
      resolveDeletionProtection({ node: { tryGetContext: () => 'maybe' } }),
    ).toThrow(/Unknown quanticDeletionProtection/);
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

function runtimePolicyDocument(template: Template): string {
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
  return JSON.stringify(policies);
}

describe('runtime IAM scope', () => {
  const template = synthesize();
  const defaultModel = chatModels['nova-pro'];

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
    expect(document).toContain(`inference-profile/${defaultModel.inferenceProfileId}`);
    expect(document).toContain('logs:PutLogEvents');
    expect(document).not.toContain('secretsmanager:');
    expect(document).not.toContain('cafe-fausse');
    expect(document).not.toContain('"Action":"*"');
    expect(document).not.toContain('bedrock:*');
    expect(document).toContain('Sid":"XRayAccess');
    expect(document).toContain('Sid":"CloudWatchMetrics');
  });

  test('allows Converse and InvokeModel on the default chat model in every us. profile region', () => {
    const document = runtimePolicyDocument(template);
    for (const action of [
      'bedrock:InvokeModel',
      'bedrock:InvokeModelWithResponseStream',
      'bedrock:Converse',
      'bedrock:ConverseStream',
    ]) {
      expect(document).toContain(`"${action}"`);
    }
    for (const region of ['us-east-1', 'us-east-2', 'us-west-2']) {
      expect(document).toContain(
        `arn:aws:bedrock:${region}::foundation-model/${defaultModel.foundationModelId}`,
      );
    }
    expect(document).toContain(
      `arn:aws:bedrock:us-east-2::foundation-model/${quanticConfig.embeddingModelId}`,
    );
    expect(document).not.toContain('claude-sonnet');
  });

  test('scopes the role to Claude Sonnet 4.6 instead when quanticChatModel=claude-sonnet-4-6', () => {
    const document = runtimePolicyDocument(synthesize({ quanticChatModel: 'claude-sonnet-4-6' }));
    expect(document).toContain('inference-profile/us.anthropic.claude-sonnet-4-6');
    expect(document).toContain('arn:aws:bedrock:us-west-2::foundation-model/anthropic.claude-sonnet-4-6');
    expect(document).not.toContain('nova-pro');
  });

  test('rejects an unknown chat model', () => {
    expect(() =>
      resolveChatModel({ node: { tryGetContext: () => 'claude-sonnet-4-5' } }),
    ).toThrow(/Unknown quanticChatModel/);
  });
});

describe('AgentCore agent runtime (default image)', () => {
  const template = synthesize();
  const json = JSON.stringify(template.toJSON());

  test('runs the repository Dockerfile image in the VPC with the HTTP contract', () => {
    template.resourceCountIs('AWS::BedrockAgentCore::Runtime', 1);
    template.hasResourceProperties('AWS::BedrockAgentCore::Runtime', {
      AgentRuntimeName: quanticConfig.agentRuntimeName,
      NetworkConfiguration: { NetworkMode: 'VPC' },
      ProtocolConfiguration: 'HTTP',
      AgentRuntimeArtifact: {
        ContainerConfiguration: { ContainerUri: Match.anyValue() },
      },
    });
    expect(json).toContain('cdk-hnb659fds-container-assets');
    expect(json).not.toContain('AWS::BedrockAgentCore::Gateway');
  });

  test('passes model, region and IAM database settings, no secrets', () => {
    const runtimes = Object.values(template.findResources('AWS::BedrockAgentCore::Runtime')) as Array<{
      Properties: { EnvironmentVariables: Record<string, unknown> };
    }>;
    const env = runtimes[0].Properties.EnvironmentVariables;
    expect(env.BEDROCK_CHAT_INFERENCE_PROFILE).toBe('us.amazon.nova-pro-v1:0');
    expect(env.BEDROCK_EMBEDDING_MODEL).toBe(quanticConfig.embeddingModelId);
    expect(env.AWS_REGION).toBe('us-east-2');
    expect(env.DB_NAME).toBe('quantic_hr_agent');
    expect(env.DB_USER).toBe('quantic_hr_agent');
    expect(env.DB_IAM_AUTH).toBe('true');
    expect(JSON.stringify(env.DB_HOST)).toContain('Endpoint.Address');
    expect(JSON.stringify(env)).not.toMatch(/secret|password/i);
  });

  test('lets the runtime role pull only from the asset repository', () => {
    const document = runtimePolicyDocument(template);
    expect(document).toContain('ecr:BatchGetImage');
    expect(document).toContain('cdk-hnb659fds-container-assets');
  });

  test('rejects an unknown runtime image', () => {
    expect(() =>
      resolveRuntimeImage({ node: { tryGetContext: () => 'latest' } }),
    ).toThrow(/Unknown quanticRuntimeImage/);
  });
});

describe('AgentCore Hello World fallback', () => {
  const template = synthesize({ quanticRuntimeImage: 'hello-world' });
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
    expect(json).not.toContain('container-assets');
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
