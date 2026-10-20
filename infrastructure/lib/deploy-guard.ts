import { quanticConfig } from './config';

export class DeployTargetError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'DeployTargetError';
  }
}

export interface DeployTarget {
  project: string;
  account: string;
  region: string;
  stackName: string;
}

export function assertSafeDeployTarget(target: DeployTarget): void {
  if (target.project !== quanticConfig.project) {
    throw new DeployTargetError(
      `Refusing project "${target.project}". Expected ${quanticConfig.project}.`,
    );
  }

  if (target.account !== quanticConfig.account) {
    throw new DeployTargetError(
      `Refusing AWS account ${target.account}. Expected ${quanticConfig.account}.`,
    );
  }

  if (target.region !== quanticConfig.region) {
    throw new DeployTargetError(
      `Refusing region ${target.region}. Expected ${quanticConfig.region}.`,
    );
  }

  const blocked = quanticConfig.blockedStackNames.find(
    (name) => name.toLowerCase() === target.stackName.toLowerCase(),
  );
  if (blocked) {
    throw new DeployTargetError(
      `Refusing stack ${target.stackName}. Café Fausse and AEA stacks stay untouched.`,
    );
  }

  if (target.stackName !== quanticConfig.stackName) {
    throw new DeployTargetError(
      `Refusing stack ${target.stackName}. Expected ${quanticConfig.stackName}.`,
    );
  }
}

export interface AvailabilityZone {
  name: string;
  id: string;
}

export function assertAgentCoreAvailabilityZones(
  zones: readonly AvailabilityZone[],
  selectedNames: readonly string[],
): void {
  const selectedIds = selectedNames.map((name) => {
    const zone = zones.find((candidate) => candidate.name === name);
    if (!zone) {
      throw new DeployTargetError(
        `Availability zone ${name} is not present in ${quanticConfig.region}.`,
      );
    }
    return zone.id;
  });

  const required = [...quanticConfig.agentCoreAvailabilityZoneIds].sort();
  const actual = [...selectedIds].sort();
  if (required.join(',') !== actual.join(',')) {
    throw new DeployTargetError(
      `Zones ${selectedNames.join(', ')} map to ${actual.join(', ')}. AgentCore needs ${required.join(', ')}.`,
    );
  }
}
