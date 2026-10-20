import { Construct } from 'constructs';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as logs from 'aws-cdk-lib/aws-logs';
import * as rds from 'aws-cdk-lib/aws-rds';

import { bedrockInvokeResourceArns, quanticConfig } from '../config';

export interface AgentRuntimeRoleProps {
  cluster: rds.IDatabaseCluster;
}

export class AgentRuntimeRole extends Construct {
  public readonly role: iam.Role;
  public readonly logGroup: logs.LogGroup;

  constructor(scope: Construct, id: string, props: AgentRuntimeRoleProps) {
    super(scope, id);

    const account = quanticConfig.account;
    const region = quanticConfig.region;

    this.role = new iam.Role(this, 'Role', {
      roleName: 'quantic-hr-agent-dev-runtime',
      assumedBy: new iam.ServicePrincipal('bedrock-agentcore.amazonaws.com', {
        conditions: {
          StringEquals: {
            'aws:SourceAccount': account,
          },
          ArnLike: {
            'aws:SourceArn': `arn:aws:bedrock-agentcore:${region}:${account}:*`,
          },
        },
      }),
      description: 'Execution role for the Quantic AgentCore runtime. No Café or AEA resources.',
    });

    this.role.addToPolicy(
      new iam.PolicyStatement({
        sid: 'InvokeSelectedBedrockModels',
        actions: [
          'bedrock:InvokeModel',
          'bedrock:InvokeModelWithResponseStream',
          'bedrock:Converse',
          'bedrock:ConverseStream',
        ],
        resources: bedrockInvokeResourceArns(account),
      }),
    );

    this.role.addToPolicy(
      new iam.PolicyStatement({
        sid: 'ConnectIamDatabaseUser',
        actions: ['rds-db:connect'],
        resources: [
          `arn:aws:rds-db:${region}:${account}:dbuser:${props.cluster.clusterResourceIdentifier}/${quanticConfig.runtimeDbUsername}`,
        ],
      }),
    );

    this.logGroup = new logs.LogGroup(this, 'RuntimeLogs', {
      logGroupName: '/quantic-hr-agent/dev/runtime',
      retention: logs.RetentionDays.ONE_MONTH,
    });
    this.logGroup.grantWrite(this.role);
  }
}
