/**
 * Project-scoped settings for the independent Quantic stack.
 * Account and region match the read-only Step 0 inventory. No secrets live here.
 */
export const quanticConfig = {
  project: 'quantic-hr-agent',
  environment: 'dev',
  stackName: 'QuanticHrAgentStack',
  account: '287238357427',
  region: 'us-east-2',
  awsProfile: 'AEA-Sandbox-PowerUser',
  databaseName: 'quantic_hr',
  adminUsername: 'quantic_hr_admin',
  runtimeDbUsername: 'quantic_hr_agent',
  secretName: 'quantic-hr-agent/dev/database/admin',
  chatInferenceProfileId: 'us.anthropic.claude-sonnet-4-5-20250929-v1:0',
  chatFoundationModelId: 'anthropic.claude-sonnet-4-5-20250929-v1:0',
  embeddingModelId: 'amazon.titan-embed-text-v2:0',
  embeddingDimensions: 1024,
  blockedStackNames: ['CafeFausseApplicationStack', 'AeaSandboxStack'],
  /**
   * Zone names are not stable AZ IDs. AgentCore in us-east-2 accepts only
   * use2-az1, use2-az2, and use2-az3. The deploy guard must prove these names
   * map to use2-az1 and use2-az2 before any deploy. Synth stays offline.
   */
  availabilityZones: ['us-east-2a', 'us-east-2b'],
  agentCoreAvailabilityZoneIds: ['use2-az1', 'use2-az2'],
  vpcCidr: '10.20.0.0/16',
  adminAmiParameter:
    '/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-arm64',
} as const;

export function bedrockInvokeResourceArns(account: string): string[] {
  const profile = `arn:aws:bedrock:${quanticConfig.region}:${account}:inference-profile/${quanticConfig.chatInferenceProfileId}`;
  const embedding = `arn:aws:bedrock:${quanticConfig.region}::foundation-model/${quanticConfig.embeddingModelId}`;
  const chatRegions = ['us-east-1', 'us-east-2', 'us-west-2'];
  const chatModels = chatRegions.map(
    (region) =>
      `arn:aws:bedrock:${region}::foundation-model/${quanticConfig.chatFoundationModelId}`,
  );
  return [profile, embedding, ...chatModels];
}
