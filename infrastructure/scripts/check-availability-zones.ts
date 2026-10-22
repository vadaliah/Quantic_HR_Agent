import {
  assertAgentCoreAvailabilityZones,
  type AvailabilityZone,
} from '../lib/deploy-guard';
import { quanticConfig } from '../lib/config';

const raw = process.argv[2];
if (!raw) {
  throw new Error(
    'Pass describe-availability-zones JSON: [{ "name": "us-east-2a", "id": "use2-az1" }, ...]',
  );
}

const zones = JSON.parse(raw) as AvailabilityZone[];
assertAgentCoreAvailabilityZones(zones, quanticConfig.availabilityZones);
console.log(
  `Accepted ${quanticConfig.availabilityZones.join(', ')} as ${quanticConfig.agentCoreAvailabilityZoneIds.join(', ')}.`,
);
