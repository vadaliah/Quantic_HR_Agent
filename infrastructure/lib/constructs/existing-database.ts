import { Construct } from 'constructs';
import * as rds from 'aws-cdk-lib/aws-rds';

/**
 * Café Fausse Aurora is not a Quantic dependency. Constructing this used to
 * import that cluster. It now fails before any resource is created.
 */
export class ExistingCafeFausseDatabase extends Construct {
  public readonly cluster: rds.IDatabaseCluster;

  constructor(scope: Construct, id: string) {
    super(scope, id);
    this.cluster = refuseCafeFausseImport();
  }
}

function refuseCafeFausseImport(): never {
  throw new Error(
    'Refusing to import Café Fausse Aurora. Quantic uses an independent cluster and must not reference Café Fausse or AEA resources.',
  );
}
