import { CfnParameter } from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as iam from 'aws-cdk-lib/aws-iam';

import { quanticConfig } from '../config';

export interface DatabaseAccessConstructProps {
  vpc: ec2.IVpc;
  securityGroup: ec2.ISecurityGroup;
}

export class DatabaseAccessConstruct extends Construct {
  public readonly instance: ec2.Instance;

  constructor(scope: Construct, id: string, props: DatabaseAccessConstructProps) {
    super(scope, id);

    const amiId = new CfnParameter(this, 'AdminHostAmiId', {
      type: 'AWS::SSM::Parameter::Value<AWS::EC2::Image::Id>',
      default: quanticConfig.adminAmiParameter,
      description:
        'Amazon Linux 2023 ARM64 AMI. CloudFormation resolves this at deploy time so local synth stays offline.',
    });

    const role = new iam.Role(this, 'SsmRole', {
      assumedBy: new iam.ServicePrincipal('ec2.amazonaws.com'),
      managedPolicies: [
        iam.ManagedPolicy.fromAwsManagedPolicyName('AmazonSSMManagedInstanceCore'),
      ],
    });

    this.instance = new ec2.Instance(this, 'AccessHost', {
      vpc: props.vpc,
      vpcSubnets: {
        subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS,
      },
      securityGroup: props.securityGroup,
      instanceType: ec2.InstanceType.of(ec2.InstanceClass.T4G, ec2.InstanceSize.NANO),
      machineImage: ec2.MachineImage.genericLinux({
        [quanticConfig.region]: amiId.valueAsString,
      }),
      role,
    });
  }
}
