# PostgreSQL RDS Parameters Sync
Compare PostgreSQL settings between two databases to detect drift.

## Features

### Audit particular settings
Example:
```bash
$ pgrdsparamsync audit --parameters=max_wal_size
```

It will get all the databases in the account and region and display their `max_wal_size` value. 
Since this can be an expensive operation, a local 1 hour cache is used for each parameter group.

If only a subset of databases is of interest, `--db-name-like` can be used to filter based on the database name.

Example:
```bash
$ pgrdsparamsync audit --parameters=max_wal_size,min_wal_size --db-name-like=production
```

It will audit only the databases that contain the string "production" in their name and display `max_wal_size` and `min_wal_size`.


### Compare a database to another or a parameter group
Example:
```bash
$ pgrdsparamsync rds-compare --target-db="users-production" --other-db="orders-production"
```

It will print all the settings that differ between the two databases.

If the goal is to set a standard against the entire database fleet, it is possible to compare a database to a parameter group that represents that standard.

Example:
```bash
$ pgrdsparamsync rds-compare --target-db="users-production" --parameter-group="pg-11-standard"
```

It will print all the settings that differ between the target database and the parameter group.


### Compare two databases directly
Example:
```bash
$ pgrdsparamsync pg-compare \
--target-db-url="postgres://user:password@users-production.rds.awsamazon.com" \
--other-db-url="postgres://user:password@orders-production.rds.awsamazom.com"
```

RDS parameter groups use formulas to calculate certain settings (e.g. `shared_buffers`, `effective_cache_size`, etc.) by default. Sometimes, it is useful to know the actual value. This will connect to the databases directly, query `pg_settings`, and print the settings that differ.


### Caching
Fetching parameter groups for 100s of databases is long and expensive. We added a local cache with a 1h TTL. It's stored in `/tmp/cache.db`. The first run of the application will be slow, but subsequent runs will be much faster.
