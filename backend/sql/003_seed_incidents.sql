-- 002_seed_incidents.sql
-- Seed 50+ sample incidents across common failure types

-- 1. Python libraries not available
INSERT INTO incidents (service, error_log, root_cause, resolution, validated) VALUES
('Glue', 'ModuleNotFoundError: No module named pandas', 'Required library not packaged with job', 'Added pandas to job dependencies', TRUE),
('EMR', 'ImportError: No module named numpy', 'Missing numpy library in cluster', 'Installed numpy via bootstrap script', TRUE),
('Lambda', 'ImportError: requests not found', 'Library not included in deployment package', 'Bundled requests in Lambda layer', TRUE),
('Glue', 'ImportError: pyarrow missing', 'Glue job missing pyarrow dependency', 'Added pyarrow to job config', FALSE),
('EMR', 'ImportError: scikit-learn not found', 'Cluster missing ML library', 'Installed scikit-learn via bootstrap', TRUE);

-- 2. Python libraries version mismatch
INSERT INTO incidents (service, error_log, root_cause, resolution, validated) VALUES
('Glue', 'Version conflict: boto3 1.20 vs botocore 1.18', 'Library version mismatch between dependencies', 'Aligned versions in requirements.txt', TRUE),
('Lambda', 'Dependency conflict: requests 2.25 vs urllib3 1.26', 'Incompatible library versions', 'Updated requirements and redeployed', TRUE),
('EMR', 'PySpark job failed due to incompatible pyarrow version', 'Version mismatch between pyarrow and pandas', 'Downgraded pyarrow to compatible version', TRUE),
('Glue', 'Conflict: numpy 1.19 vs scipy 1.7', 'Library versions not aligned', 'Updated requirements to match versions', FALSE),
('Lambda', 'Conflict: boto3 vs botocore mismatch', 'Lambda deployment package outdated', 'Rebuilt package with consistent versions', TRUE);

-- 3. Code compilation issues
INSERT INTO incidents (service, error_log, root_cause, resolution, validated) VALUES
('Lambda', 'SyntaxError: invalid syntax in handler.py', 'Code compilation error', 'Fixed syntax and redeployed function', TRUE),
('EMR', 'PySpark job failed: NameError in script', 'Unresolved variable in code', 'Corrected code and re-ran job', TRUE),
('Glue', 'Compilation error: unexpected indent', 'Python indentation issue', 'Fixed indentation and re-ran job', TRUE),
('API Gateway', 'Deployment failed: invalid JSON in mapping template', 'Malformed template', 'Corrected JSON and redeployed', TRUE),
('Lambda', 'Compilation error: missing colon', 'Syntax error in code', 'Fixed syntax and redeployed', FALSE);

-- 4. File landed with wrong extension
INSERT INTO incidents (service, error_log, root_cause, resolution, validated) VALUES
('S3', 'Received .txt file instead of .csv', 'Incorrect file extension in event trigger', 'Updated S3 event filter to accept .txt', FALSE),
('S3', 'File extension .json not supported', 'Unexpected file type landed in bucket', 'Modified ingestion pipeline to handle .json', TRUE),
('S3', 'File landed with .xml extension', 'Pipeline expected .csv', 'Added XML parser to ingestion job', TRUE),
('S3', 'File landed with .parquet instead of .csv', 'Event misconfigured', 'Updated Glue job to handle parquet', TRUE),
('S3', 'Unsupported extension .log', 'Log file dropped into data bucket', 'Moved logs to separate bucket', TRUE);

-- 5. SNS and Lambda integration failure
INSERT INTO incidents (service, error_log, root_cause, resolution, validated) VALUES
('SNS', 'Message not delivered to Lambda', 'IAM role missing invoke permissions', 'Updated IAM policy to allow Lambda invocation', TRUE),
('Lambda', 'Event trigger not firing', 'SNS subscription misconfigured', 'Re-subscribed Lambda to SNS topic', TRUE),
('SNS', 'Delivery failure: endpoint disabled', 'Lambda function disabled', 'Re-enabled Lambda and retried', TRUE),
('Lambda', 'SNS event payload malformed', 'Incorrect JSON schema', 'Fixed schema and retried', FALSE),
('SNS', 'Subscription confirmation failed', 'Endpoint not responding', 'Manually confirmed subscription', TRUE);

-- 6. Lambda and EMR/Glue trigger failure
INSERT INTO incidents (service, error_log, root_cause, resolution, validated) VALUES
('Lambda', 'Failed to trigger Glue job', 'Glue job ARN misconfigured', 'Corrected ARN and retried trigger', TRUE),
('Lambda', 'EMR cluster not starting', 'Cluster configuration missing', 'Updated cluster config and retried', FALSE),
('Lambda', 'Glue job trigger timed out', 'Network issue', 'Retried with increased timeout', TRUE),
('Lambda', 'Trigger failed: invalid IAM role', 'Role missing permissions', 'Updated IAM role', TRUE),
('Lambda', 'Trigger failed: EMR cluster not found', 'Cluster ID incorrect', 'Corrected cluster ID', TRUE);

-- 7. File size too high
INSERT INTO incidents (service, error_log, root_cause, resolution, validated) VALUES
('Glue', 'File size exceeds 5GB limit', 'Large file caused memory overflow', 'Partitioned file into smaller chunks', TRUE),
('EMR', 'Job failed due to oversized dataset', 'Cluster insufficient resources', 'Scaled cluster nodes and re-ran job', TRUE),
('Glue', 'OutOfMemoryError: file too large', 'Job exceeded memory allocation', 'Increased worker memory', TRUE),
('EMR', 'Dataset too large for single executor', 'Executor memory insufficient', 'Increased executor count', TRUE),
('Glue', 'File size exceeded 10GB', 'Job timed out', 'Split file into partitions', FALSE);

-- 8. Athena table not queryable
INSERT INTO incidents (service, error_log, root_cause, resolution, validated) VALUES
('Athena', 'Query failed: HIVE_PARTITION_SCHEMA_MISMATCH', 'Schema mismatch in partitioned table', 'Updated table schema in Glue catalog', TRUE),
('Athena', 'Query timed out', 'Large dataset without partitioning', 'Added partitions and optimized query', TRUE),
('Athena', 'Query failed: column not found', 'Schema drift', 'Updated schema in Glue catalog', TRUE),
('Athena', 'Query failed: invalid data type', 'Column type mismatch', 'Corrected schema', TRUE),
('Athena', 'Query failed: corrupted data', 'Bad records in S3', 'Cleaned data and reloaded', FALSE);

-- 9. Athena table not accessible to end user
INSERT INTO incidents (service, error_log, root_cause, resolution, validated) VALUES
('Athena', 'Permission denied for SELECT', 'IAM policy missing Athena access', 'Granted SELECT permissions to user role', TRUE),
('Athena', 'Table not visible to analyst', 'Glue catalog permissions missing', 'Updated Glue catalog access policy', TRUE),
('Athena', 'Access denied: user not authorized', 'IAM role missing permissions', 'Updated IAM role', TRUE),
('Athena', 'Table hidden due to catalog sync issue', 'Catalog not refreshed', 'Ran MSCK REPAIR TABLE', TRUE),
('Athena', 'Access denied: cross-account user', 'Cross-account permissions missing', 'Added resource policy', FALSE);

-- 10. Glue catalog issues
INSERT INTO incidents (service, error_log, root_cause, resolution, validated) VALUES
('Glue', 'Catalog table missing columns', 'Schema drift not updated in catalog', 'Altered table schema in Glue catalog', TRUE),
('Glue', 'Catalog not syncing with S3', 'Outdated metadata in catalog', 'Ran MSCK REPAIR TABLE to refresh partitions', TRUE),
('Glue', 'Catalog corrupted', 'Metadata inconsistency', 'Rebuilt catalog table', TRUE),
('Glue', 'Catalog missing partitions', 'Partition discovery failed', 'Ran repair table command', TRUE),
('Glue', 'Catalog permissions denied', 'IAM role missing access', 'Updated IAM role', FALSE);

-- 11. Spark job failure
INSERT INTO incidents (service, error_log, root_cause, resolution, validated) VALUES
('EMR', 'Spark job failed: java.lang.OutOfMemoryError', 'Insufficient executor memory', 'Increased executor memory allocation', TRUE),
('EMR', 'Spark job failed: Task not serializable', 'Serialization issue in user-defined function', 'Refactored code to avoid serialization error', TRUE),
('EMR', 'Spark job failed: Shuffle error', 'Insufficient disk space', 'Increased disk space and retried', TRUE),
('EMR', 'Spark job failed: Stage aborted', 'Data skew issue', 'Repartitioned data', TRUE),
('EMR', 'Spark job failed: ClassNotFoundException', 'Missing dependency jar', 'Added jar to classpath', TRUE);
