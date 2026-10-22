import { assertSafeDeployTarget } from '../lib/deploy-guard';

assertSafeDeployTarget({
  project: process.env.QUANTIC_PROJECT ?? '',
  account: process.env.QUANTIC_ACCOUNT ?? '',
  region: process.env.QUANTIC_REGION ?? '',
  stackName: process.env.QUANTIC_STACK_NAME ?? '',
});

console.log(
  `Accepted ${process.env.QUANTIC_STACK_NAME} in ${process.env.QUANTIC_ACCOUNT}/${process.env.QUANTIC_REGION}.`,
);
