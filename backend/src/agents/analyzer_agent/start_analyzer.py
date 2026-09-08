import json
import logging
import os

from src.agents.analyzer_agent import AnalyzerStore, RCAAnalyzerAgent
from src.agents.analyzer_agent.log_providers import FlociLogProvider

logging.basicConfig(level=logging.INFO)


class FlociClient:
    def fetch_logs(self, service, resource, start, end, pattern=None):
        # Replace with your actual Floci client.
        return []


def main() -> None:
    store = AnalyzerStore()
    log_provider = FlociLogProvider(FlociClient())

    agent = RCAAnalyzerAgent(
        db=store,
        log_provider=log_provider,
    )

    try:
        result = agent.analyze(
            incident_query=os.getenv(
                "INCIDENT_QUERY",
                """Job ERROR : aggregate_clickstream ,
                    Error: TaskSetManager: Task 7 in stage 45.0 failed 4 times; aborting job
                    java.lang.OutOfMemoryError: Java heap space
                        at org.apache.spark.util.collection.unsafe.sort.UnsafeExternalSorter.allocateMemory(UnsafeExternalSorter.java:210)
                        at org.apache.spark.util.collection.unsafe.sort.UnsafeExternalSorter.insertAll(UnsafeExternalSorter.java:320)
                        at org.apache.spark.shuffle.sort.SortShuffleWriter.write(SortShuffleWriter.scala:63)
                        at org.apache.spark.scheduler.ShuffleMapTask.runTask(ShuffleMapTask.scala:99)
                        at org.apache.spark.scheduler.ShuffleMapTask.runTask(ShuffleMapTask.scala:52)
                        at org.apache.spark.scheduler.Task.run(Task.scala:123)
                        at org.apache.spark.executor.Executor$TaskRunner.run(Executor.scala:345)
                        """
            ),
        )
        print(json.dumps(result, indent=2, default=str))
    finally:
        agent.close()


if __name__ == "__main__":
    main()