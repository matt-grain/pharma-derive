## Points to check

1. Persistence

- For local testing without docker, important to have an adaptation layer (SQLAlchemy?) to support storage in sqlite or postgresql
- States persistence, requirements mention json file for short term, I don't think that's production ready (if multiple instance) so probably database persistence required
- DAG persistence

2. Deployment

- As we are going to implement the docker co,mpose scenario, we need an option to support  monoinstance/no docker/multiple python processes for testing on local conmputer

3. Code quality

- add vulture for dead-code (usually happen after refactoring)
- create specific review agents: cybersec, pydanticAI, fastapi, "what can go wrong agent"
- CI:
  - pre-commit same rules on github
  - pytest with coverage check
- CD:
  - inactivated script to deploy to cloud
  - rollback: add a manual GH to rollback? (usually I would use IaC but we can do a simple action I guess)


4. Cybersec

document clearly the restrictions
- Access control
  - no auth and multi-tenancy, can be added easily on top of API / OAuth based on Sanofi existing solutions
  - no data segregation
- Encryption
  - SSL supported with docker for communications (outbound)
  - No database encyption (can be enabled)
- (raw) Data exposure
  - Real data vs synthetic data seen by agent
  - tools data access
  - audit log on data access

5. From prototype to prod

- Scalability
  - Easy path to Kubernetes to create on-demand pod for the orchestration core => horizontal scalability per run
  - the rest of the architecture is already production ready (with horizontal and vertical scalability): Postgresql, reverse proxy
  - parallel processing within a run outside the orchestration pattern? (databtrick/spark instead of postgresql?)

6. processing versioning
  - YAML
  - DAG metadata 
  - ADaM data linked to DAG


7. Reliability Failure mode / error propagation



## Open questions:

11. D. Scaling Use Cases => multi-modal: what does it mean?



