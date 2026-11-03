#!/usr/bin/env bash
# The empty database is the Aurora cluster default database, quantic_hr_agent.
# This script must not connect to Café Fausse or AEA, and it does not create schemas.
echo "BLOCKED: quantic_hr_agent is created only by the independent Quantic Aurora cluster."
echo "Refusing to create a database on Café Fausse, AEA, or any other existing cluster."
exit 1
