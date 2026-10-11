import os
import time
from pathlib import Path
from dotenv import load_dotenv

# 1. Load .env from project root
env_path = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(env_path)

# Set default project_id if not provided
if not os.getenv("AGENTOPS_PROJECT_ID"):
    os.environ["AGENTOPS_PROJECT_ID"] = "synthetic-demo"

from agentops_sdk import AgentOps
from agentops_sdk.adapters.decorator import observe_agent

# 2. Initialize the SDK from environment variables
agentops = AgentOps.from_env()

# 2. Instrument using a decorator
@observe_agent(agentops, agent_id="simple-agent-1")
def run_my_agent(query: str):
    print(f"Agent received query: {query}")
    time.sleep(0.5) # Simulate work
    
    if "error" in query.lower():
        raise ValueError("Simulated an error during execution!")
        
    return {"response": f"Processed {query} successfully", "secret": "shh"}

if __name__ == "__main__":
    print("--- Running Successful Agent ---")
    try:
        run_my_agent("Hello World")
    except Exception as e:
        print(f"Error: {e}")
        
    print("\n--- Running Failing Agent ---")
    try:
        run_my_agent("Cause an error")
    except Exception as e:
        print(f"Error: {e}")
        
    # Flush remaining telemetry before exiting
    print("\nShutting down SDK...")
    agentops.shutdown()
