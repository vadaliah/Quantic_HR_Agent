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
  /** Matches the Data API migration runner, migration 003 and the README. */
  databaseName: 'quantic_hr_agent',
  adminUsername: 'quantic_hr_admin',
  runtimeDbUsername: 'quantic_hr_agent',
  secretName: 'quantic-hr-agent/dev/database/admin',
  /** Default chat model key; override with `-c quanticChatModel=claude-sonnet-4-6`. See chatModels below. */
  defaultChatModel: 'nova-pro',
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
  helloWorldRuntimeName: 'QuanticHelloWorld',
  adminAmiParameter:
    '/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-arm64',
} as const;

/**
 * One chat model is used at a time. The app reads the matching inference profile
 * from BEDROCK_CHAT_INFERENCE_PROFILE; the CDK runtime role is scoped to the same
 * model through `-c quanticChatModel=<key>`. Keep the two in step.
 *
 * Verified in us-east-2 on 2026-11-11 (model catalog, not account access):
 * - nova-pro: ACTIVE through the us. profile only. Default (team decision 2026-11-11).
 *   Access in 287238357427 is not yet confirmed (docs/STEP0_AWS_FINDINGS.md lists
 *   only Titan and Claude): confirm it is enabled there before any deploy.
 * - claude-sonnet-4-6: ACTIVE through the us. profile. Selectable alternative.
 * Claude Sonnet 4.5 is marked LEGACY in Bedrock and is no longer offered here.
 */
export const chatModels = {
  'claude-sonnet-4-6': {
    inferenceProfileId: 'us.anthropic.claude-sonnet-4-6',
    foundationModelId: 'anthropic.claude-sonnet-4-6',
  },
  'nova-pro': {
    inferenceProfileId: 'us.amazon.nova-pro-v1:0',
    foundationModelId: 'amazon.nova-pro-v1:0',
  },
} as const;

export type ChatModelKey = keyof typeof chatModels;
export type ChatModel = (typeof chatModels)[ChatModelKey];

/** Regions a `us.` cross-region inference profile may route a request to. */
export const usInferenceProfileRegions = ['us-east-1', 'us-east-2', 'us-west-2'] as const;

type ContextScope = { node: { tryGetContext(key: string): unknown } };

export function resolveChatModel(scope: ContextScope): ChatModel {
  const raw = String(scope.node.tryGetContext('quanticChatModel') ?? quanticConfig.defaultChatModel);
  if (raw in chatModels) {
    return chatModels[raw as ChatModelKey];
  }
  throw new Error(
    `Unknown quanticChatModel "${raw}". Use one of: ${Object.keys(chatModels).join(', ')}.`,
  );
}

/**
 * Aurora deletion protection. Off by default: this is a time-limited dev demo and
 * `cdk destroy` must be able to remove the cluster after grading. Pass
 * `-c quanticDeletionProtection=true` to keep the cluster (and retain it on stack delete).
 */
export function resolveDeletionProtection(scope: ContextScope): boolean {
  const raw = scope.node.tryGetContext('quanticDeletionProtection');
  if (raw === undefined || raw === null || raw === '') {
    return false;
  }
  const value = String(raw).toLowerCase();
  if (['true', 'yes', '1'].includes(value)) {
    return true;
  }
  if (['false', 'no', '0'].includes(value)) {
    return false;
  }
  throw new Error(`Unknown quanticDeletionProtection "${raw}". Use true or false.`);
}

export type DatabaseMode = 'create' | 'reuse-cafe-fausse';

/**
 * Live Café Fausse cluster identifiers from the 20 Oct 2026 read-only inventory.
 * Used only when quanticDatabaseMode=reuse-cafe-fausse. Import is by attributes
 * so synth stays offline. The cluster, secret, and security group are not updated.
 */
export const cafeFausseAurora = {
  clusterIdentifier: 'cafefausseapplicationstac-databaseaurorapostgres65-zchaodeehzxe',
  clusterResourceIdentifier: 'cluster-7D7XF4SYGRI7TSN7NJV5FNZHNA',
  securityGroupId: 'sg-09f0dd96526f3085f',
  secretName: 'cafe-fausse-application/database/admin',
  vpcId: 'vpc-0a6e62a6eae7cb617',
  port: 5432,
} as const;

export function resolveDatabaseMode(scope: ContextScope): DatabaseMode {
  const raw = String(scope.node.tryGetContext('quanticDatabaseMode') ?? 'create');
  if (raw === 'create') {
    return 'create';
  }
  if (raw === 'reuse-cafe-fausse' || raw === 'reuse') {
    return 'reuse-cafe-fausse';
  }
  throw new Error(`Unknown quanticDatabaseMode "${raw}". Use create or reuse-cafe-fausse.`);
}

/**
 * Resources the runtime may invoke: the chosen `us.` inference profile in the stack
 * region, the profile's foundation model in every region the profile can route to,
 * and Titan Text Embeddings v2 on demand in the stack region.
 */
export function bedrockInvokeResourceArns(account: string, chatModel: ChatModel): string[] {
  const profile = `arn:aws:bedrock:${quanticConfig.region}:${account}:inference-profile/${chatModel.inferenceProfileId}`;
  const embedding = `arn:aws:bedrock:${quanticConfig.region}::foundation-model/${quanticConfig.embeddingModelId}`;
  const chatFoundationModels = usInferenceProfileRegions.map(
    (region) => `arn:aws:bedrock:${region}::foundation-model/${chatModel.foundationModelId}`,
  );
  return [profile, embedding, ...chatFoundationModels];
}
