#!/usr/bin/env node
import * as cdk from 'aws-cdk-lib';

import { quanticConfig } from '../lib/config';
import { QuanticHrAgentStack } from '../lib/infrastructure-stack';

const app = new cdk.App();

new QuanticHrAgentStack(app, quanticConfig.stackName, {
  description:
    'Independent Quantic Aurora PostgreSQL database. Private subnets only. Does not create a NAT gateway or AgentCore runtime, and does not update Café Fausse or AEA stacks.',
  env: {
    account: quanticConfig.account,
    region: quanticConfig.region,
  },
});
