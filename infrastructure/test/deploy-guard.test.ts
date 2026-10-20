import { quanticConfig } from '../lib/config';
import {
  assertAgentCoreAvailabilityZones,
  assertCostFirstDeployAllowed,
  assertSafeDeployTarget,
  DeployTargetError,
} from '../lib/deploy-guard';

describe('deploy target guard', () => {
  const allowed = {
    project: quanticConfig.project,
    account: quanticConfig.account,
    region: quanticConfig.region,
    stackName: quanticConfig.stackName,
  };

  test('blocks AWS deploy until paid-infra approval', () => {
    expect(() => assertCostFirstDeployAllowed({})).toThrow(DeployTargetError);
    expect(() => assertCostFirstDeployAllowed({ QUANTIC_ALLOW_AWS_DEPLOY: 'yes' })).not.toThrow();
  });

  test('accepts the Quantic stack in the Step 0 account and region', () => {
    expect(() => assertSafeDeployTarget(allowed)).not.toThrow();
  });

  test.each(['CafeFausseApplicationStack', 'AeaSandboxStack'])(
    'refuses frozen stack %s',
    (stackName) => {
      expect(() => assertSafeDeployTarget({ ...allowed, stackName })).toThrow(DeployTargetError);
    },
  );

  test('refuses a different account, region, project, or stack', () => {
    expect(() => assertSafeDeployTarget({ ...allowed, account: '000000000000' })).toThrow(
      DeployTargetError,
    );
    expect(() => assertSafeDeployTarget({ ...allowed, region: 'us-east-1' })).toThrow(
      DeployTargetError,
    );
    expect(() => assertSafeDeployTarget({ ...allowed, project: 'cafe-fausse' })).toThrow(
      DeployTargetError,
    );
    expect(() => assertSafeDeployTarget({ ...allowed, stackName: 'SomeOtherStack' })).toThrow(
      DeployTargetError,
    );
  });
});

describe('AgentCore availability zones', () => {
  const zones = [
    { name: 'us-east-2a', id: 'use2-az1' },
    { name: 'us-east-2b', id: 'use2-az2' },
    { name: 'us-east-2c', id: 'use2-az3' },
  ];

  test('accepts the two supported zone IDs regardless of account-local names', () => {
    expect(() =>
      assertAgentCoreAvailabilityZones(zones, ['us-east-2a', 'us-east-2b']),
    ).not.toThrow();
  });

  test('refuses a name that is not use2-az1 or use2-az2', () => {
    expect(() =>
      assertAgentCoreAvailabilityZones(zones, ['us-east-2a', 'us-east-2c']),
    ).toThrow(DeployTargetError);
  });
});
