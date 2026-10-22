#!/usr/bin/env node
import * as cdk from 'aws-cdk-lib';

import { quanticConfig } from '../lib/config';
import { QuanticHrAgentStack } from '../lib/infrastructure-stack';

const app = new cdk.App();

new QuanticHrAgentStack(app, quanticConfig.stackName, {
  description:
    'Quantic baseline: VPC, IAM, AgentCore Hello World, and either a new Aurora or a read-only reference to Café Fausse Aurora. Does not update Café Fausse or AEA stacks.',
  env: {
    account: quanticConfig.account,
    region: quanticConfig.region,
  },
});
