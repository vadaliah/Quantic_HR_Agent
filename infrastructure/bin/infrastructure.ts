#!/usr/bin/env node
import * as cdk from 'aws-cdk-lib';

import { quanticConfig } from '../lib/config';
import { QuanticHrAgentStack } from '../lib/infrastructure-stack';

const app = new cdk.App();

new QuanticHrAgentStack(app, quanticConfig.stackName, {
  description: 'Independent Quantic HR agent network, Aurora, and runtime role. Does not modify Café Fausse or AEA.',
  env: {
    account: quanticConfig.account,
    region: quanticConfig.region,
  },
});
