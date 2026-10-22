import { Construct } from 'constructs';
import * as ec2 from 'aws-cdk-lib/aws-ec2';

import { quanticConfig } from '../config';

export class NetworkConstruct extends Construct {
  public readonly vpc: ec2.Vpc;
  public readonly runtimeSecurityGroup: ec2.SecurityGroup;
  public readonly adminSecurityGroup: ec2.SecurityGroup;

  constructor(scope: Construct, id: string) {
    super(scope, id);

    this.vpc = new ec2.Vpc(this, 'Vpc', {
      ipAddresses: ec2.IpAddresses.cidr(quanticConfig.vpcCidr),
      availabilityZones: [...quanticConfig.availabilityZones],
      natGateways: 1,
      subnetConfiguration: [
        {
          name: 'public',
          subnetType: ec2.SubnetType.PUBLIC,
          cidrMask: 24,
        },
        {
          name: 'private',
          subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS,
          cidrMask: 24,
        },
        {
          name: 'isolated',
          subnetType: ec2.SubnetType.PRIVATE_ISOLATED,
          cidrMask: 24,
        },
      ],
    });

    this.runtimeSecurityGroup = new ec2.SecurityGroup(this, 'RuntimeSecurityGroup', {
      vpc: this.vpc,
      description: 'AgentCore runtime ENIs. Inbound invocations do not use this group.',
      allowAllOutbound: false,
    });
    this.runtimeSecurityGroup.addEgressRule(
      ec2.Peer.anyIpv4(),
      ec2.Port.tcp(443),
      'HTTPS to Bedrock and AWS APIs through the NAT gateway',
    );

    this.adminSecurityGroup = new ec2.SecurityGroup(this, 'AdminSecurityGroup', {
      vpc: this.vpc,
      description: 'SSM database admin host. No inbound from the internet.',
      allowAllOutbound: false,
    });
    this.adminSecurityGroup.addEgressRule(
      ec2.Peer.anyIpv4(),
      ec2.Port.tcp(443),
      'HTTPS to SSM through the NAT gateway',
    );
  }
}
