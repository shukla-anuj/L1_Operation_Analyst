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
                """Job ERROR : glue job failed ,
                    Command failed with exit code 1 or An error occurred while calling...
                        """
            ),
        )
        print("<<<<<<<< Analyzer Result >>>>>>>>>")
        print(json.dumps(result, indent=2, default=str))
    finally:
        agent.close()


if __name__ == "__main__":
    main()